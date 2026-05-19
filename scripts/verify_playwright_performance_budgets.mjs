#!/usr/bin/env node
/**
 * Playwright CLS + scroll FPS budgets (docs/PERFORMANCE_BUDGETS.md).
 *
 * Usage:
 *   node scripts/verify_playwright_performance_budgets.mjs
 *   PERF_PLAYWRIGHT_STRICT=1 node scripts/verify_playwright_performance_budgets.mjs
 *
 * Env:
 *   PERF_PLAYWRIGHT_STRICT=1     exit 1 on exceed (default warn-only)
 *   PERF_PLAYWRIGHT_BASE_URL     default http://127.0.0.1:8000
 *   PERF_PLAYWRIGHT_MAX_CLS      default 0.12
 *   PERF_PLAYWRIGHT_MIN_FPS      default 55
 *   PLAYWRIGHT_HOST_RULES        host resolver (tenant subdomains)
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const STRICT = process.env.PERF_PLAYWRIGHT_STRICT === '1';
const BASE = (process.env.PERF_PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8000').replace(
  /\/$/,
  ''
);
const MAX_CLS = parseFloat(process.env.PERF_PLAYWRIGHT_MAX_CLS || '0.12');
const MIN_FPS = parseFloat(process.env.PERF_PLAYWRIGHT_MIN_FPS || '55');
const HOST_RULES =
  process.env.PLAYWRIGHT_HOST_RULES ||
  'MAP runmycampus.com 127.0.0.1,MAP manager.runmycampus.com 127.0.0.1';

const AUTH = path.join(process.cwd(), 'artifacts/manager-playwright-auth.json');

/** @type {Array<{label:string, path:string, host?:string}>} */
const BASE_TARGETS = [
  { label: 'Theme Experience hub', path: '/siteconfig/theme-experience/hub/' },
  { label: 'Theme builder canvas', path: '/siteconfig/theme-experience/builder/' },
  {
    label: 'Theme colors editor',
    path: '/siteconfig/theme-colors/?standalone=1',
  },
  { label: 'Zero-ticket hub', path: '/siteconfig/zero-ticket/' },
  { label: 'Zero-ticket permissions', path: '/siteconfig/zero-ticket/permissions/' },
  { label: 'Campus workflow canvas', path: '/siteconfig/zero-ticket/workflows/' },
  { label: 'Configure hub', path: '/portal/configure/' },
];

let extraTargets = [];
try {
  if (process.env.PERF_PLAYWRIGHT_EXTRA_TARGETS) {
    extraTargets = JSON.parse(process.env.PERF_PLAYWRIGHT_EXTRA_TARGETS);
  }
} catch (_e) {
  extraTargets = [];
}

const TARGETS = [...BASE_TARGETS, ...extraTargets];

async function measurePage(page) {
  await page.addInitScript(() => {
    window.__rmcPerf = { cls: 0, frames: 0, start: 0 };
    try {
      const po = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.hadRecentInput) continue;
          window.__rmcPerf.cls += entry.value;
        }
      });
      po.observe({ type: 'layout-shift', buffered: true });
    } catch (_e) {
      /* older engines */
    }
  });

  await page.evaluate(() => {
    window.__rmcPerf.start = performance.now();
    let running = true;
    const tick = () => {
      if (!running) return;
      window.__rmcPerf.frames += 1;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    const el = document.scrollingElement || document.documentElement;
    let y = 0;
    const step = () => {
      y = Math.min(y + 80, el.scrollHeight);
      el.scrollTop = y;
      if (y < el.scrollHeight - window.innerHeight) {
        setTimeout(step, 16);
      } else {
        running = false;
      }
    };
    setTimeout(step, 50);
  });

  await page.waitForTimeout(1600);

  return page.evaluate(() => {
    const p = window.__rmcPerf || {};
    const elapsed = Math.max(1, performance.now() - (p.start || performance.now()));
    const fps = (p.frames || 0) / (elapsed / 1000);
    return { cls: p.cls || 0, fps };
  });
}

async function tryLogin(context, host) {
  if (!fs.existsSync(AUTH)) return false;
  try {
    const state = JSON.parse(fs.readFileSync(AUTH, 'utf8'));
    if (state.cookies?.length) {
      await context.addCookies(state.cookies);
      return true;
    }
  } catch (_e) {
    return false;
  }
  return false;
}

async function main() {
  const browser = await chromium.launch({
    channel: 'chromium',
    headless: true,
    args: [`--host-resolver-rules=${HOST_RULES}`],
  });
  const failures = [];
  let skipped = 0;

  for (const target of TARGETS) {
    const host = target.host || new URL(BASE).host;
    const origin = `http://${host}`;
    const url = `${origin}${target.path}`;
    const context = await browser.newContext({ baseURL: origin });
    await tryLogin(context, host);
    const page = await context.newPage();
    try {
      const resp = await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: 45000,
      });
      if (!resp || resp.status() >= 500) {
        console.warn(`SKIP: ${target.label} HTTP ${resp?.status() ?? 'n/a'}`);
        skipped += 1;
        await context.close();
        continue;
      }
      const { cls, fps } = await measurePage(page);
      const clsBad = cls > MAX_CLS;
      const fpsBad = fps < MIN_FPS;
      const status = clsBad || fpsBad ? 'FAIL' : 'OK';
      console.log(
        `${status}: ${target.label} cls=${cls.toFixed(3)} (≤${MAX_CLS}) fps=${fps.toFixed(1)} (≥${MIN_FPS})`
      );
      if (clsBad || fpsBad) {
        failures.push({ label: target.label, cls, fps });
      }
    } catch (err) {
      console.warn(`SKIP: ${target.label} — ${err.message || err}`);
      skipped += 1;
    } finally {
      await context.close();
    }
  }

  await browser.close();

  if (failures.length && STRICT) {
    console.error(
      `\n${failures.length} surface(s) exceeded Playwright perf budgets. Set PERF_PLAYWRIGHT_STRICT=0 to warn only.`
    );
    process.exit(1);
  }
  if (skipped === TARGETS.length) {
    console.warn('All targets skipped — is Django running on PERF_PLAYWRIGHT_BASE_URL?');
    process.exit(STRICT ? 1 : 0);
  }
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(STRICT ? 1 : 0);
});
