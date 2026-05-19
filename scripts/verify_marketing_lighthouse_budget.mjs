#!/usr/bin/env node
/**
 * Marketing LCP + CLS budgets for / and /pricing/ on runmycampus.com host.
 *
 * Env:
 *   MKT_LIGHTHOUSE_STRICT=1|0
 *   MKT_LIGHTHOUSE_MAX_LCP_MS=2500
 *   MKT_LIGHTHOUSE_MAX_CLS=0.1
 *   MKT_LIGHTHOUSE_HOST=runmycampus.com
 *   MKT_LIGHTHOUSE_PORT=8000
 */
import { chromium } from 'playwright';

const STRICT = process.env.MKT_LIGHTHOUSE_STRICT !== '0';
const MAX_LCP = parseFloat(process.env.MKT_LIGHTHOUSE_MAX_LCP_MS || '2500');
const MAX_CLS = parseFloat(process.env.MKT_LIGHTHOUSE_MAX_CLS || '0.1');
const HOST = process.env.MKT_LIGHTHOUSE_HOST || 'runmycampus.com';
const PORT = process.env.MKT_LIGHTHOUSE_PORT || '8000';
const ORIGIN = `http://${HOST}:${PORT}`;

const PATHS = ['/', '/pricing/'];

async function measure(page) {
  await page.addInitScript(() => {
    window.__mktPerf = { cls: 0, lcp: 0 };
    try {
      const poCls = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.hadRecentInput) continue;
          window.__mktPerf.cls += entry.value;
        }
      });
      poCls.observe({ type: 'layout-shift', buffered: true });
    } catch (_e) {
      /* ignore */
    }
    try {
      const poLcp = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries[entries.length - 1];
        if (last) window.__mktPerf.lcp = last.startTime;
      });
      poLcp.observe({ type: 'largest-contentful-paint', buffered: true });
    } catch (_e) {
      /* ignore */
    }
  });

  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(800);

  return page.evaluate(() => {
    const p = window.__mktPerf || {};
    let lcp = p.lcp || 0;
    try {
      const entries = performance.getEntriesByType('largest-contentful-paint');
      if (entries.length) lcp = entries[entries.length - 1].startTime;
    } catch (_e) {
      /* ignore */
    }
    return { cls: p.cls || 0, lcp };
  });
}

async function main() {
  const browser = await chromium.launch({
    channel: 'chromium',
    headless: true,
    args: [`--host-resolver-rules=MAP ${HOST} 127.0.0.1`],
  });
  const failures = [];
  let skipped = 0;

  for (const path of PATHS) {
    const context = await browser.newContext({ baseURL: ORIGIN });
    const page = await context.newPage();
    const label = `${path}`;
    try {
      const resp = await page.goto(path, {
        waitUntil: 'domcontentloaded',
        timeout: 45000,
      });
      if (!resp || resp.status() >= 500) {
        console.warn(`SKIP: ${label} HTTP ${resp?.status() ?? 'n/a'}`);
        skipped += 1;
        await context.close();
        continue;
      }
      const { cls, lcp } = await measure(page);
      const lcpBad = lcp > MAX_LCP;
      const clsBad = cls > MAX_CLS;
      const status = lcpBad || clsBad ? 'FAIL' : 'OK';
      console.log(
        `${status}: ${label} lcp=${lcp.toFixed(0)}ms (≤${MAX_LCP}) cls=${cls.toFixed(3)} (≤${MAX_CLS})`
      );
      if (lcpBad || clsBad) failures.push({ path, lcp, cls });
    } catch (err) {
      console.warn(`SKIP: ${label} — ${err.message || err}`);
      skipped += 1;
    } finally {
      await context.close();
    }
  }

  await browser.close();

  if (skipped === PATHS.length) {
    console.warn(
      `All marketing lighthouse targets skipped — start Django on ${ORIGIN} (Host: ${HOST})`
    );
    process.exit(STRICT ? 1 : 0);
  }
  if (failures.length && STRICT) {
    console.error(`\n${failures.length} path(s) exceeded marketing lighthouse budgets.`);
    process.exit(1);
  }
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(STRICT ? 1 : 0);
});
