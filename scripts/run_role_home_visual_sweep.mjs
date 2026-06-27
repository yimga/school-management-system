#!/usr/bin/env node
/**
 * Focused abrupt-end sweep: parent / teacher / student / admin / marketing threshold-era.
 * Uses tests/e2e/helpers/tenant-login.js (path-tenant 127.0.0.1 + MFA TOTP) — batch 1701 harness.
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';

const ROOT = process.cwd();
if (!process.env.VISUAL_QA_PYTHON) {
  const winVenv = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
  const unixVenv = path.join(ROOT, '.venv', 'bin', 'python');
  if (fs.existsSync(winVenv)) {
    process.env.VISUAL_QA_PYTHON = winVenv;
  } else if (fs.existsSync(unixVenv)) {
    process.env.VISUAL_QA_PYTHON = unixVenv;
  }
}

const PORT = process.env.VISUAL_QA_PORT || '8012';
process.env.VISUAL_QA_PORT = PORT;
const TENANT_SLUG = process.env.TENANT_SLUG || 'demo-school';
if (process.env.TENANT_E2E_SUBDOMAIN === undefined) {
  process.env.TENANT_E2E_SUBDOMAIN = '1';
}
if (!process.env.TENANT_E2E_BASE_URL) {
  process.env.TENANT_E2E_BASE_URL =
    process.env.TENANT_E2E_SUBDOMAIN === '1'
      ? `http://${TENANT_SLUG}.runmycampus.com:${PORT}`
      : `http://127.0.0.1:${PORT}/t/${TENANT_SLUG}`;
}

const require = createRequire(import.meta.url);
const { loginTenant, TENANT_BASE_URL } = require('../tests/e2e/helpers/tenant-login.js');

const MKT_HOST = process.env.MARKETING_SWEEP_HOST || 'runmycampus.com';
const MKT_BASE =
  process.env.MARKETING_SWEEP_BASE || `http://${MKT_HOST}:${PORT}`;
const TENANT_ONLY = process.env.ROLE_SWEEP_TENANT_ONLY === '1';
const P0_MENUS = process.env.ROLE_SWEEP_P0_MENUS === '1';
const OUT = path.join(
  process.cwd(),
  P0_MENUS ? 'var/tenant-menu-p0-sweep.json' : 'var/role-home-visual-sweep.json',
);
const P0_SURFACES_PATH = path.join(
  process.cwd(),
  'docs/generated/tenant_p0_menu_sweep_surfaces.json',
);

const HOST_RESOLVER_RULES =
  process.env.PLAYWRIGHT_ROLE_SWEEP_HOST_RULES ||
  'MAP runmycampus.com 127.0.0.1,' +
    'MAP demo-school.runmycampus.com 127.0.0.1,' +
    'MAP manager.runmycampus.com 127.0.0.1,' +
    'MAP *.runmycampus.com 127.0.0.1';

function chromiumLaunchArgs() {
  return [
    `--host-resolver-rules=${HOST_RESOLVER_RULES}`,
    '--proxy-server=direct://',
    '--proxy-bypass-list=*',
    '--disable-features=HttpsUpgrades,HttpsFirstMode',
  ];
}

function sweepPageInBrowser(scrollRootSel) {
  function findScrollable(el) {
    if (!el) return null;
    const style = window.getComputedStyle(el);
    if (
      (style.overflowY === 'auto' ||
        style.overflowY === 'scroll' ||
        style.overflowY === 'overlay') &&
      el.scrollHeight > el.clientHeight + 2
    ) {
      return el;
    }
    for (let i = 0; i < el.children.length; i++) {
      const found = findScrollable(el.children[i]);
      if (found) return found;
    }
    return el;
  }
  function countStranded() {
    let stranded = 0;
    document.querySelectorAll('.rmc-reveal').forEach((el) => {
      if (el.classList.contains('is-revealed')) return;
      if (parseFloat(getComputedStyle(el).opacity) < 0.05) stranded += 1;
    });
    return stranded;
  }
  const roots = scrollRootSel
    ? [document.querySelector(scrollRootSel)]
    : [
        document.querySelector('#main-content'),
        document.querySelector('main'),
        document.querySelector('.rmc-app-shell__canvas-body'),
      ];
  const main = findScrollable(roots.find(Boolean) || null);
  const body = document.body;
  const bodyOY = body ? getComputedStyle(body).overflowY : '';
  const canScroll = !!(main && main.scrollHeight > main.clientHeight + 2);
  if (canScroll) {
    main.scrollTop = Math.max(0, main.scrollHeight - main.clientHeight);
    main.dispatchEvent(new Event('scroll', { bubbles: true }));
  }
  const strandedAfter = countStranded();
  const trapped =
    bodyOY === 'hidden' &&
    body &&
    body.scrollHeight > body.clientHeight + 80 &&
    main &&
    !(main.scrollHeight > main.clientHeight + 2);
  const failures = [];
  if (trapped) failures.push('body_scroll_trapped');
  if (main && main.scrollHeight > main.clientHeight + 100 && strandedAfter > 0) {
    failures.push(`scrollable_but_stranded_${strandedAfter}`);
  }
  return {
    path: location.pathname,
    title: document.title,
    armed: document.documentElement.getAttribute('data-rmc-reveal-armed'),
    revealTotal: document.querySelectorAll('.rmc-reveal').length,
    strandedAfter,
    failures,
    ok: failures.length === 0,
    canScroll,
  };
}

const DEMO_PREFIX = process.env.TENANT_DEMO_USERNAME_PREFIX || 'demo';
const DEMO_PASS = process.env.TENANT_SWEEP_PASSWORD || 'Test1234';

async function probeTenantServer(baseUrl) {
  const http = await import('node:http');
  let hostHeader = `${TENANT_SLUG}.runmycampus.com:${PORT}`;
  try {
    hostHeader = new URL(baseUrl.replace(/\/$/, '')).host;
  } catch (_e) {
    /* keep default host header */
  }
  const probePath = `/t/${TENANT_SLUG}/authentication/login/`;
  return new Promise((resolve) => {
    const req = http.get(
      {
        hostname: '127.0.0.1',
        port: PORT,
        path: probePath,
        headers: { Host: hostHeader },
      },
      (res) => {
        res.resume();
        resolve(res.statusCode ?? 0);
      },
    );
    req.on('error', () => resolve(0));
    req.setTimeout(8000, () => {
      req.destroy();
      resolve(0);
    });
  });
}

async function waitForTenantServer(baseUrl, maxSeconds = 120) {
  for (let i = 0; i < maxSeconds; i += 1) {
    const code = await probeTenantServer(baseUrl);
    if (code >= 200 && code < 500) {
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`tenant server not ready at ${baseUrl}`);
}

const SURFACES = [
  {
    label: 'parent-home',
    url: '/portal/parent/',
    user: `${DEMO_PREFIX}.parent`,
    pass: DEMO_PASS,
  },
  {
    label: 'teacher-home',
    url: '/portal/teacher/',
    user: `${DEMO_PREFIX}.teacher`,
    pass: DEMO_PASS,
  },
  {
    label: 'student-grades',
    url: '/portal/student-portal/grades/',
    user: `${DEMO_PREFIX}.student`,
    pass: DEMO_PASS,
  },
  {
    label: 'admin-backend',
    url: '/authentication/backend/',
    user: `${DEMO_PREFIX}.admin`,
    pass: DEMO_PASS,
  },
  {
    label: 'admin-performance',
    url: '/authentication/backend/performance/',
    user: `${DEMO_PREFIX}.admin`,
    pass: DEMO_PASS,
  },
];

function loadP0MenuSurfaces() {
  if (!fs.existsSync(P0_SURFACES_PATH)) {
    console.error(`missing ${P0_SURFACES_PATH} — run python scripts/generate_tenant_p0_menu_sweep_surfaces.py --write`);
    process.exit(1);
  }
  const payload = JSON.parse(fs.readFileSync(P0_SURFACES_PATH, 'utf8'));
  const rows = payload.surfaces || [];
  return rows.map((row) => ({
    label: row.label,
    url: row.url,
    user: row.user,
    pass: DEMO_PASS,
    p0Menu: true,
  }));
}

let activeSurfaces = SURFACES;
if (P0_MENUS) {
  const p0 = loadP0MenuSurfaces();
  const includeHomes = process.env.ROLE_SWEEP_P0_INCLUDE_HOMES !== '0';
  activeSurfaces = includeHomes ? [...SURFACES, ...p0] : p0;
}

if (!TENANT_ONLY) {
  activeSurfaces.push(
    {
      label: 'marketing-threshold',
      url: '/experience/threshold-era/',
      base: MKT_BASE,
      host: MKT_HOST,
      anon: true,
      scrollRoot: 'main',
    },
    {
      label: 'marketing-home',
      url: '/',
      base: MKT_BASE,
      host: MKT_HOST,
      anon: true,
      scrollRoot: 'main',
    },
  );
}

const browser = await chromium.launch({
  headless: true,
  args: chromiumLaunchArgs(),
});
const results = [];

for (const s of activeSurfaces) {
  if (P0_MENUS && results.length > 0) {
    await new Promise((r) => setTimeout(r, 3000));
  }
  const base = s.base || TENANT_BASE_URL;
  if (!s.anon) {
    await waitForTenantServer(base);
  }
  const ctxOpts = {
    baseURL: base,
    viewport: { width: 1400, height: 900 },
  };
  const ctx = await browser.newContext(ctxOpts);
  const page = await ctx.newPage();
  const row = { label: s.label, requested: s.url, base, host: s.host || null };
  try {
    if (!s.anon) {
      await loginTenant(page, { username: s.user, password: s.pass });
      row.loginPath = new URL(page.url()).pathname;
    }
    const response = await page.goto(s.url, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    row.httpStatus = response ? response.status() : null;
    if (row.httpStatus && row.httpStatus >= 400) {
      row.failures = [`http_${row.httpStatus}`];
      row.ok = false;
      results.push(row);
      await ctx.close();
      continue;
    }
    const title = await page.title();
    if (/page not found|404|not found at/i.test(title)) {
      row.failures = ['page_not_found'];
      row.ok = false;
      results.push(row);
      await ctx.close();
      continue;
    }
    if (
      !s.anon &&
      /\/authentication\/login\/?$/i.test(new URL(page.url()).pathname)
    ) {
      row.failures = [...(row.failures || []), 'session_lost_login_redirect'];
      row.ok = false;
      results.push(row);
      await ctx.close();
      continue;
    }
    await page.waitForTimeout(1200);
    const TENANT_CHROME_LABELS = new Set([
      'parent-home',
      'teacher-home',
      'student-grades',
      'admin-backend',
      'admin-performance',
    ]);
    const needsChrome =
      TENANT_CHROME_LABELS.has(s.label) ||
      (s.p0Menu && !s.anon);
    if (needsChrome) {
      await page.waitForTimeout(600);
      row.chrome = await page.evaluate(() => ({
        tenantToolsIsland: !!document.getElementById('page-data-rmc-tenant-tools'),
        toolsEdgeTab: !!document.querySelector('.rmc-operator-tools__edge-tab'),
        copilotRail: !!document.querySelector('[data-rmc-copilot-rail]'),
        copilotExpandedPanel: !!document.querySelector('.lx-copilot__expanded'),
        tenantHeader100x: !!document.querySelector('[data-rmc-tenant-header-100x="1"]'),
        tpPrimaryNavInline: !!document.querySelector('[data-rmc-tenant-primary-nav-inline="1"]'),
        actionsEmptyState: !!document.querySelector('[data-rmc-copilot-rail-actions-empty]'),
        previewLive: !!document.querySelector(
          '[data-rmc-preview-live-admin="1"], [data-rmc-preview-live-teacher="1"], [data-rmc-preview-live-parent="1"], [data-rmc-preview-live-student="1"]',
        ),
      }));
      if (!row.chrome.tenantToolsIsland) {
        row.failures = [...(row.failures || []), 'tenant_tools_island_missing'];
        row.ok = false;
      }
      if (!row.chrome.copilotRail) {
        row.failures = [...(row.failures || []), 'tenant_copilot_rail_missing'];
        row.ok = false;
      }
      if (!row.chrome.tenantHeader100x) {
        row.failures = [...(row.failures || []), 'tenant_header_100x_missing'];
        row.ok = false;
      }
      const isRoleHomeChrome = TENANT_CHROME_LABELS.has(s.label);
      if (isRoleHomeChrome && !row.chrome.previewLive) {
        row.failures = [...(row.failures || []), 'tenant_preview_live_surface_missing'];
        row.ok = false;
      }
      const edgeTab = page.locator('.rmc-operator-tools__edge-tab');
      const edgeCount = await edgeTab.count();
      if (row.chrome.tenantToolsIsland && edgeCount > 0) {
        await edgeTab.first().click({ timeout: 15000 });
        await page.waitForTimeout(400);
        row.chrome.toolsTrayOpen = await page.evaluate(() => {
          const tray = document.getElementById('rmcOperatorToolsTray');
          if (!tray || tray.getAttribute('aria-hidden') !== 'false') return false;
          return !!(
            tray.querySelector('.rmc-operator-tools__group') ||
            tray.querySelector('[data-rmc-tools-tray-empty]') ||
            tray.querySelector('[data-rmc-assist-slot-id]')
          );
        });
        if (isRoleHomeChrome && !row.chrome.toolsTrayOpen) {
          row.failures = [...(row.failures || []), 'tenant_tools_tray_open_failed'];
          row.ok = false;
        }
        await edgeTab.first().click({ timeout: 5000 }).catch(() => {});
      } else if (row.chrome.tenantToolsIsland && edgeCount === 0) {
        row.failures = [...(row.failures || []), 'tenant_tools_edge_tab_missing'];
        row.ok = false;
      }
      if (s.label === 'admin-backend') {
        row.chrome.adminBento = await page.evaluate(() => {
          const pageWrap = document.querySelector('.portal-main-col > .page-wrap');
          const wrapStyle = pageWrap ? getComputedStyle(pageWrap) : null;
          return {
            bento: !!document.querySelector('[data-rmc-admin-bento]'),
            overviewPanel: !!document.getElementById('rmc-admin-bento-overview'),
            cockpitPanel: !!document.getElementById('rmc-admin-bento-cockpit'),
            setupZoneIntro: !!document.querySelector(
              '[data-rmc-admin-zone="setup"], [data-rmc-admin-zone="cockpit"]',
            ),
            previewLiveAdmin: !!document.querySelector('[data-rmc-preview-live-admin="1"]'),
            tpV3Shell: document.documentElement.getAttribute('data-rmc-tp-v3-shell') === '1',
            pageExplainCount: document.querySelectorAll('[data-rmc-page-explain="1"]').length,
            nextActionStripCount: document.querySelectorAll('[data-rmc-next-action-strip="1"]').length,
            missionStrip: !!document.querySelector('[data-rmc-tp-mission="1"]'),
            pageWrapMinHeight: wrapStyle ? wrapStyle.minHeight : null,
            mfaNudgeCount: document.querySelectorAll('[data-rmc-mfa-nudge="1"]').length,
            communityBandCount: document.querySelectorAll(
              '[data-rmc-cockpit-section="community_band"]',
            ).length,
            newsletterBandCount: document.querySelectorAll(
              '[data-rmc-cockpit-section="newsletter_band"]',
            ).length,
          };
        });
        const b = row.chrome.adminBento;
        if (b?.tpV3Shell) {
          if (b.pageExplainCount > 0) {
            row.failures = [...(row.failures || []), 'legacy_page_explain_on_v3'];
            row.ok = false;
          }
          if (b.nextActionStripCount > 0) {
            row.failures = [...(row.failures || []), 'duplicate_next_action_on_v3'];
            row.ok = false;
          }
          if (b.mfaNudgeCount > 0) {
            row.failures = [...(row.failures || []), 'legacy_mfa_nudge_on_v3'];
            row.ok = false;
          }
          if (b.communityBandCount > 0) {
            row.failures = [...(row.failures || []), 'legacy_community_band_on_v3'];
            row.ok = false;
          }
          if (b.newsletterBandCount > 0) {
            row.failures = [...(row.failures || []), 'legacy_newsletter_band_on_v3'];
            row.ok = false;
          }
          const minH = b.pageWrapMinHeight || '';
          if (minH.includes('calc') && minH.includes('dvh')) {
            row.failures = [...(row.failures || []), 'page_wrap_void_slab'];
            row.ok = false;
          }
        }
      }
    }
    const scrollRoot = s.scrollRoot || '#main-content';
    let audit = await page.evaluate(sweepPageInBrowser, scrollRoot);
    await page.waitForTimeout(500);
    audit = await page.evaluate(sweepPageInBrowser, scrollRoot);
    Object.assign(row, audit);
    if (s.label === 'marketing-threshold') {
      row.marketing = await page.evaluate(() => ({
        ascGate: !!document.querySelector('.mkt-asc-gate'),
        ascDay: !!document.querySelector('.mkt-asc-day'),
        trustNav: !!document.querySelector('.mkt-rev-trust-nav'),
        parentCard: !!document.querySelector('.mkt-asc-parent-card'),
      }));
      if (!row.marketing.ascGate || !row.marketing.trustNav) {
        row.failures = [...(row.failures || []), 'marketing_content_missing'];
        row.ok = false;
      }
    }
    if (s.label === 'marketing-home') {
      row.marketing = await page.evaluate(() => ({
        oneRecordScroll: !!document.querySelector('[data-mkt-one-record-scroll]'),
        chapters: document.querySelectorAll('.mkt-or__chapter').length,
        stagePanels: document.querySelectorAll('.mkt-or__panel').length,
      }));
      if (!row.marketing.oneRecordScroll || row.marketing.chapters < 6 || row.marketing.stagePanels < 6) {
        row.failures = [...(row.failures || []), 'one_record_scroll_missing'];
        row.ok = false;
      }
    }
  } catch (e) {
    row.ok = false;
    row.failures = ['exception'];
    row.error = String(e).slice(0, 300);
  }
  results.push(row);
  await ctx.close();
}
await browser.close();

const payload = {
  generatedAt: new Date().toISOString(),
  tenantBase: TENANT_BASE_URL,
  marketingBase: MKT_BASE,
  marketingHost: MKT_HOST,
  tenantOnly: TENANT_ONLY,
  p0Menus: P0_MENUS,
  passed: results.filter((r) => r.ok !== false).length,
  failed: results.filter((r) => r.ok === false).length,
  results,
};
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(payload, null, 2) + '\n');
console.log(JSON.stringify(payload, null, 2));
process.exit(payload.failed ? 1 : 0);
