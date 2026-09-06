#!/usr/bin/env node
/**
 * Authenticated browser evidence for control-plane surfaces.
 *
 * Real Chromium, real password login, real TOTP step-up (via the repo's own
 * tests/e2e/helpers/manager-login.js). No middleware is disabled, no session flag
 * is written behind the login form's back.
 *
 * Every row records the HTTP status of the NAVIGATION, the final URL after any
 * redirect, and a measurement of the main content region so an empty shell is
 * distinguishable from a rendered page.
 *
 *   node artifacts/cplane-browser-evidence/capture_control_plane_evidence.js
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const {
  loginManager,
  MANAGER_BASE_URL,
  MANAGER_HOST,
} = require('../../tests/e2e/helpers/manager-login');

const OUT_DIR = __dirname;
const SHOT_DIR = path.join(OUT_DIR, 'screenshots');
const RESULT_JSON = path.join(OUT_DIR, 'evidence.json');

const hostRules =
  process.env.PLAYWRIGHT_HOST_RULES || `MAP ${MANAGER_HOST} 127.0.0.1`;
const PLAYWRIGHT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

const SURFACES = [
  { name: 'super-dashboard', path: '/super/' },
  { name: 'super-schools', path: '/super/schools/' },
  { name: 'super-command-center', path: '/super/command-center/' },
  { name: 'django-admin-index', path: '/admin/' },
  { name: 'super-founder', path: '/super/founder/' },
];

const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'laptop', width: 1280, height: 800 },
  { name: 'desktop', width: 1920, height: 1080 },
];
const THEMES = ['light', 'dark'];
const THEME_KEY = 'runmycampus-theme-preference';

async function setTheme(page, preference) {
  await page.evaluate(
    ({ key, pref }) => {
      try {
        localStorage.setItem(key, pref);
      } catch (_e) {
        /* ignore */
      }
      if (window.RMCTheme && typeof window.RMCTheme.set === 'function') {
        window.RMCTheme.set(pref);
      } else {
        document.documentElement.setAttribute('data-theme', pref);
        document.documentElement.setAttribute('data-resolved-theme', pref);
        document.documentElement.setAttribute('data-bs-theme', pref);
        document.documentElement.classList.toggle('dark', pref === 'dark');
      }
    },
    { key: THEME_KEY, pref: preference }
  );
}

/** Measure the main content region; an empty shell must not read as a render. */
async function measure(page) {
  return page.evaluate(() => {
    const main =
      document.querySelector('#cp-main-content') ||
      document.querySelector('[data-rmc-shell-main]') ||
      document.querySelector('main') ||
      document.querySelector('#content') ||
      document.body;
    const rect = main ? main.getBoundingClientRect() : null;
    const text = main ? (main.innerText || '').trim() : '';
    const style = main ? getComputedStyle(main) : null;
    return {
      mainSelector: main ? (main.id ? '#' + main.id : main.tagName.toLowerCase()) : null,
      mainVisible: Boolean(
        main &&
          style &&
          style.display !== 'none' &&
          style.visibility !== 'hidden' &&
          rect &&
          rect.width > 0 &&
          rect.height > 0
      ),
      mainWidth: rect ? Math.round(rect.width) : 0,
      mainHeight: rect ? Math.round(rect.height) : 0,
      mainTextChars: text.length,
      mainTextSample: text.slice(0, 160).replace(/\s+/g, ' '),
      headings: main ? main.querySelectorAll('h1,h2,h3').length : 0,
      links: main ? main.querySelectorAll('a[href]').length : 0,
      tables: main ? main.querySelectorAll('table').length : 0,
      forms: main ? main.querySelectorAll('form').length : 0,
      buttons: main ? main.querySelectorAll('button, [role="button"]').length : 0,
      resolvedTheme:
        document.documentElement.getAttribute('data-resolved-theme') ||
        document.documentElement.getAttribute('data-theme') ||
        null,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      bodyColor: getComputedStyle(document.body).color,
      title: document.title,
      docScrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
    };
  });
}

async function main() {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  const base = MANAGER_BASE_URL.replace(/\/$/, '');
  const browser = await chromium.launch({
    channel: 'chromium',
    args: [
      `--host-resolver-rules=${hostRules}`,
      '--proxy-server=direct://',
      '--proxy-bypass-list=*',
      '--disable-features=HttpsUpgrades,HttpsFirstMode',
    ],
  });
  const context = await browser.newContext({
    baseURL: base,
    userAgent: PLAYWRIGHT_UA,
    viewport: { width: 1400, height: 900 },
  });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 300));
  });

  console.log('[evidence] logging in (real password + real TOTP)…');
  await loginManager(page);
  console.log('[evidence] logged in; landed on', page.url());

  const rows = [];
  const fullMatrix = process.env.EVIDENCE_FULL_MATRIX === '1';
  const viewports = fullMatrix ? VIEWPORTS : [VIEWPORTS[2]];
  const themes = fullMatrix ? THEMES : ['light'];

  for (const surface of SURFACES) {
    for (const vp of viewports) {
      for (const theme of themes) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        const url = base + surface.path;
        let status = null;
        let error = null;
        let respHeaders = {};
        const before = consoleErrors.length;
        try {
          const resp = await page.goto(url, {
            waitUntil: 'domcontentloaded',
            timeout: 60000,
          });
          status = resp ? resp.status() : null;
          respHeaders = resp ? await resp.headers() : {};
          await setTheme(page, theme);
          await page.waitForTimeout(600);
        } catch (e) {
          error = String(e.message || e).slice(0, 300);
        }
        let m = {};
        try {
          m = await measure(page);
        } catch (e) {
          error = (error || '') + ' measure:' + String(e.message || e).slice(0, 200);
        }
        const finalUrl = page.url();
        const finalPath = (() => {
          try {
            return new URL(finalUrl).pathname;
          } catch (_e) {
            return '';
          }
        })();
        const redirectedToAuth =
          /\/authentication\/(login|mfa)/i.test(finalPath) ||
          /\/mfa\//i.test(finalPath);
        const shot = path.join(
          SHOT_DIR,
          `${surface.name}__${vp.name}__${theme}.png`
        );
        try {
          await page.screenshot({ path: shot, fullPage: false });
        } catch (_e) {
          /* ignore */
        }
        rows.push({
          surface: surface.name,
          requestedPath: surface.path,
          host: MANAGER_HOST,
          role: 'SUPERADMIN (visualqa_admin)',
          viewport: vp.name,
          viewportSize: `${vp.width}x${vp.height}`,
          theme,
          httpStatus: status,
          finalUrl,
          finalPath,
          redirectedToAuth,
          rendered:
            status === 200 &&
            !redirectedToAuth &&
            Boolean(m.mainVisible) &&
            Number(m.mainTextChars || 0) > 200,
          csp: {
            reportOnly: respHeaders['content-security-policy-report-only'] || null,
            enforcing: respHeaders['content-security-policy'] || null,
            isAdminPolicy: /unsafe-eval/.test(
              respHeaders['content-security-policy-report-only'] || ''
            ),
          },
          measurement: m,
          screenshot: path.relative(path.join(__dirname, '../..'), shot),
          consoleErrors: consoleErrors.slice(before, before + 5),
          error,
        });
        console.log(
          `[evidence] ${surface.name} ${vp.name}/${theme} → HTTP ${status} ` +
            `path=${finalPath} chars=${m.mainTextChars} rendered=${rows[rows.length - 1].rendered} ` + `csp=${rows[rows.length - 1].csp.reportOnly ? 'report-only' : (rows[rows.length - 1].csp.enforcing ? 'enforcing' : 'NONE')}` + `${rows[rows.length - 1].csp.isAdminPolicy ? '(admin)' : ''}`
        );
      }
    }
  }

  fs.writeFileSync(RESULT_JSON, JSON.stringify({ base, rows }, null, 2), 'utf8');
  await browser.close();
  console.log(`[evidence] wrote ${RESULT_JSON} (${rows.length} rows)`);
  const bad = rows.filter((r) => !r.rendered);
  if (bad.length) {
    console.log(`[evidence] NOT rendered: ${bad.length}/${rows.length}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
