#!/usr/bin/env node
/**
 * Platform sweep: control-plane / admin changelist / tenant portal — abrupt-end
 * + stranded rmc-reveal. Writes NDJSON to debug-7911e1.log; exits 1 on layout failures.
 *
 * Usage:
 *   python scripts/generate_control_plane_sweep_routes.py --write
 *   python scripts/generate_portal_tenant_sweep_routes.py --write
 *   SWEEP_TIER=operator+admin node scripts/verify_platform_abrupt_end_sweep.mjs
 *   bash scripts/run_platform_abrupt_end_sweep.sh
 *
 * Env:
 *   SWEEP_TIER=operator | operator+admin | tenant | all (default operator)
 *   SWEEP_PATHS=comma-separated path prefixes (manager routes; tenant uses SWEEP_TENANT_PATHS)
 *   SWEEP_TENANT_PATHS=comma prefixes for tenant JSON routes only (if unset, all tenant routes)
 *   SWEEP_GOTO_RETRIES=3  SWEEP_GOTO_MS=90000
 *   SWEEP_VIEWPORT_WIDTH=768  SWEEP_VIEWPORT_HEIGHT=1024 (tablet proof; default 1400x900)
 *
 * Git Bash: export MSYS_NO_PATHCONV=1 when passing SWEEP_* URL lists, or rely on
 * built-in undo for `C:/Program Files/Git/...` and `T:/...` → `/t/...` munging.
 *
 * Requires Django on MANAGER_BASE_URL (default http://manager.runmycampus.com:8012)
 * and TENANT_BASE_URL for tenant surfaces (default http://demo-school.runmycampus.com:8012).
 * Host resolver: MAP manager.runmycampus.com 127.0.0.1 and tenant subdomain.
 */
import { chromium } from 'playwright';
import fs from 'fs';
import http from 'http';
import path from 'path';
import crypto from 'crypto';
import { execFileSync } from 'child_process';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const {
  loginManager,
  AUTH_STATE_PATH,
} = require('../tests/e2e/helpers/manager-login');
const { loginTenant: loginTenantMfa, ensurePathTenantHost } = require('../tests/e2e/helpers/tenant-login');

const LOG = path.join(process.cwd(), 'debug-7911e1.log');
const SESSION = '7911e1';
const HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const PORT = process.env.VISUAL_QA_PORT || '8012';
const BASE = process.env.MANAGER_BASE_URL || `http://${HOST}:${PORT}`;
const TENANT_SLUG = process.env.TENANT_SWEEP_SLUG || 'demo-school';
const TENANT_HOST =
  process.env.VISUAL_QA_TENANT_HOST || `${TENANT_SLUG}.runmycampus.com`;
const USE_TENANT_SUBDOMAIN =
  (process.env.USE_TENANT_SUBDOMAIN || '1').toLowerCase() !== '0';
const TENANT_BASE =
  process.env.TENANT_BASE_URL ||
  process.env.TENANT_E2E_BASE_URL ||
  process.env.PLAYWRIGHT_TENANT_BASE_URL ||
  (USE_TENANT_SUBDOMAIN
    ? `http://${TENANT_HOST}:${PORT}`
    : `http://127.0.0.1:${PORT}`);
const AUTH = AUTH_STATE_PATH;
const HOST_RULES =
  process.env.PLAYWRIGHT_HOST_RULES || `MAP ${HOST} 127.0.0.1`;

function chromiumLaunchArgs(hostRules) {
  return [
    `--host-resolver-rules=${hostRules}`,
    '--proxy-server=direct://',
    '--proxy-bypass-list=*',
    '--disable-features=HttpsUpgrades,HttpsFirstMode',
  ];
}
const ROUTES_JSON = path.join(
  process.cwd(),
  'docs/generated/control_plane_sweep_routes.json'
);
const TENANT_ROUTES_JSON = path.join(
  process.cwd(),
  'docs/generated/portal_tenant_sweep_routes.json'
);
const TENANT_ADMIN_ROUTES_JSON = path.join(
  process.cwd(),
  'docs/generated/tenant_admin_sweep_routes.json'
);

const GOTO_RETRIES = Math.max(1, parseInt(process.env.SWEEP_GOTO_RETRIES || '3', 10));
const GOTO_TIMEOUT = parseInt(process.env.SWEEP_GOTO_MS || '90000', 10);
const SWEEP_VIEWPORT = {
  width: Math.max(320, parseInt(process.env.SWEEP_VIEWPORT_WIDTH || '1400', 10)),
  height: Math.max(480, parseInt(process.env.SWEEP_VIEWPORT_HEIGHT || '900', 10)),
};

/** Git Bash / MSYS maps `/foo/` to `C:/Program Files/Git/foo/` and `/t/...` to `T:/...`. */
function normalizeSweepPathList(raw) {
  if (!raw) return [];
  const msysGit = /^[A-Za-z]:\/Program Files\/Git\//i;
  return raw
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      let x = p.replace(/\\/g, '/');
      if (msysGit.test(x)) {
        x = x.replace(msysGit, '/');
      }
      const msysDriveT = /^T:\/(.*)/i;
      const tDrive = msysDriveT.exec(x);
      if (tDrive) {
        x = `/t/${tDrive[1]}`;
      }
      if (!x.startsWith('/')) x = `/${x}`;
      return x;
    });
}

/** @type {Array<{surface:string,url:string,scrollRoot?:string,login?:'manager'|'tenant'|'none'}>} */
const FALLBACK_SURFACES = [
  // Manager control plane — user-reported + certification routes
  { surface: 'manager', url: '/configuration/' },
  { surface: 'manager', url: '/super/analytics/' },
  { surface: 'manager', url: '/super/migration/' },
  { surface: 'manager', url: '/super/support/' },
  { surface: 'manager', url: '/super/' },
  { surface: 'manager', url: '/super/marketplace/' },
  { surface: 'manager', url: '/super/marketplace/apps/' },
  { surface: 'manager', url: '/super/marketplace/blueprints/' },
  { surface: 'manager', url: '/super/workflow-packs/' },
  { surface: 'manager', url: '/super/dashboard-packs/' },
  { surface: 'manager', url: '/super/security/' },
  { surface: 'manager', url: '/super/schools/' },
  { surface: 'manager', url: '/super/create/' },
  { surface: 'manager', url: '/super/command-center/' },
  { surface: 'manager', url: '/super/trust/' },
  { surface: 'manager', url: '/configuration/blueprints/' },
  { surface: 'manager', url: '/configuration/workflow-packs/' },
  { surface: 'manager', url: '/configuration/dashboard-packs/' },
  { surface: 'manager', url: '/configuration/change-requests/' },
  { surface: 'manager', url: '/configuration/registries/' },
  { surface: 'manager', url: '/configuration/registries/health/' },
  { surface: 'manager', url: '/configuration/migrations/' },
  { surface: 'manager', url: '/configuration/integrations/' },
  { surface: 'manager', url: '/configuration/billing/' },
  { surface: 'manager', url: '/configuration/experience/' },
  { surface: 'manager', url: '/admin/' },
  { surface: 'manager', url: '/admin/schools/school/' },
  { surface: 'manager', url: '/admin/integrations_marketplace/marketplaceapp/' },
  { surface: 'manager', url: '/admin/compliance/auditlog/' },
  // Tenant portal (path-based demo school)
  {
    surface: 'tenant',
    url: '/t/demo-school/authentication/backend/',
    scrollRoot: '#main-content',
    login: 'tenant',
  },
  {
    surface: 'tenant',
    url: '/t/demo-school/siteconfig/guided-onboarding/?embed=1',
    scrollRoot: '#main-content',
    login: 'tenant',
  },
  {
    surface: 'tenant',
    url: '/school/studio/',
    scrollRoot: '#main-content',
    login: 'tenant',
  },
  {
    surface: 'tenant',
    url: '/school/studio/setup/',
    scrollRoot: '#main-content',
    login: 'tenant',
  },
];

function loadManagerSurfaces() {
  if (!fs.existsSync(ROUTES_JSON)) {
    return FALLBACK_SURFACES.filter((s) => s.surface === 'manager');
  }
  const tierFilter = process.env.SWEEP_TIER || 'operator';
  const data = JSON.parse(fs.readFileSync(ROUTES_JSON, 'utf8'));
  const routes = Array.isArray(data.routes) ? data.routes : [];
  const pathFilter = normalizeSweepPathList(process.env.SWEEP_PATHS || '');
  return routes
    .filter((row) => row.sweep !== false)
    .filter((row) => {
      if (pathFilter.length) {
        const exact = process.env.SWEEP_PATHS_EXACT === '1';
        const matches = exact
          ? pathFilter.some((p) => row.path === p)
          : pathFilter.some((p) => row.path.startsWith(p));
        if (!matches) return false;
      }
      if (tierFilter === 'all') return true;
      if (tierFilter === 'admin_changelist') {
        return row.tier === 'admin_changelist';
      }
      if (tierFilter === 'operator+admin') {
        return row.tier === 'operator' || row.tier === 'admin_changelist';
      }
      return !row.tier || row.tier === 'operator';
    })
    .map((row) => ({
      surface: 'manager',
      url: row.path,
    }));
}

function loadTenantSurfaces() {
  const pathFilter = normalizeSweepPathList(process.env.SWEEP_PATHS || '');
  const tenantOnlyFilter = normalizeSweepPathList(
    process.env.SWEEP_TENANT_PATHS || ''
  );
  const manifest = SWEEP_TIER === 'admin_changelist'
    ? TENANT_ADMIN_ROUTES_JSON
    : TENANT_ROUTES_JSON;
  if (!fs.existsSync(manifest)) {
    if (SWEEP_TIER === 'admin_changelist') {
      return [
        { surface: 'tenant', url: '/admin/', login: 'tenant' },
        { surface: 'tenant', url: '/admin/academics/', login: 'tenant' },
        { surface: 'tenant', url: '/admin/academics/academicyear/', login: 'tenant' },
        { surface: 'tenant', url: '/admin/academics/academicyear/add/', login: 'tenant' },
      ];
    }
    return FALLBACK_SURFACES.filter((s) => s.surface === 'tenant');
  }
  const data = JSON.parse(fs.readFileSync(manifest, 'utf8'));
  const routes = Array.isArray(data.routes) ? data.routes : [];
  const maxRoutes = parseInt(process.env.TENANT_SWEEP_MAX || '0', 10);
  const capped = maxRoutes > 0 ? routes.slice(0, maxRoutes) : routes;
  return capped
    .filter((row) => row.sweep !== false)
    .filter((row) => {
      const p = row.path;
      if (tenantOnlyFilter.length) {
        return tenantOnlyFilter.some((x) => p.startsWith(x));
      }
      if (pathFilter.length) {
        const exact = process.env.SWEEP_PATHS_EXACT === '1';
        if (exact) {
          return pathFilter.some((x) => p === x || row.inner === x);
        }
        return pathFilter.some((x) => p.startsWith(x));
      }
      return true;
    })
    .map((row) => {
      const inner = row.inner || row.path.replace(`/t/${TENANT_SLUG}/`, '/');
      const url = USE_TENANT_SUBDOMAIN ? inner : row.path;
      return {
        surface: 'tenant',
        url,
        inner,
        scrollRoot: '#main-content',
        login: 'tenant',
      };
    });
}

const INCLUDE_TENANT =
  (process.env.SWEEP_INCLUDE_TENANT || '1').toLowerCase() !== '0';
const SWEEP_TIER = process.env.SWEEP_TIER || 'operator';
const SURFACES = [
  ...(SWEEP_TIER !== 'tenant' ? loadManagerSurfaces() : []),
  ...(INCLUDE_TENANT ? loadTenantSurfaces() : []),
];
const ROUTE_SETTLE_MS = Math.max(
  100,
  parseInt(
    process.env.SWEEP_ROUTE_SETTLE_MS ||
      (SWEEP_TIER === 'admin_changelist' ? '300' : '1200'),
    10
  )
);
const ROUTE_STABILITY_MS = Math.max(
  50,
  parseInt(process.env.SWEEP_ROUTE_STABILITY_MS || '150', 10)
);
const ROUTE_CONCURRENCY = Math.max(
  1,
  Math.min(8, parseInt(process.env.SWEEP_ROUTE_CONCURRENCY || '4', 10))
);

function isInfraOrNonHtmlSkip(error) {
  const e = String(error || '');
  return (
    /ERR_CONNECTION|ERR_CONNECTION_TIMED_OUT|ERR_CONNECTION_REFUSED|Timeout \d+ms exceeded/i.test(
      e
    ) ||
    /Download is starting/i.test(e) ||
    /interrupted by another navigation/i.test(e)
  );
}

function sleepMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sha256File(file) {
  return fs.existsSync(file)
    ? crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
    : null;
}

function gitValue(args, fallback = 'unavailable') {
  try {
    return execFileSync('git', args, { cwd: process.cwd(), encoding: 'utf8' }).trim();
  } catch (_error) {
    return fallback;
  }
}

async function auditAdminViewportMatrix(page, { surface, expectedHost, expectedSite, artifactDir }) {
  const rows = [];
  for (const width of [1440, 1024, 768, 390]) {
    for (const theme of ['light', 'dark']) {
      await page.setViewportSize({ width, height: width <= 390 ? 844 : 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      const response = await gotoWithRetries(page, '/admin/');
      await page.waitForTimeout(500);
      const metrics = await page.evaluate(({ expectedHost, expectedSite }) => {
        const visible = (node) => {
          if (!node) return false;
          const style = getComputedStyle(node);
          const rect = node.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };
        const styles = Array.from(document.querySelectorAll('link[rel~="stylesheet"]'));
        const styleUrls = styles.map((node) => node.href);
        const contractNode = document.querySelector('#rmcAdminNavigationContract');
        let contract = null;
        try { contract = contractNode ? JSON.parse(contractNode.textContent || '{}') : null; } catch (_error) { contract = null; }
        return {
          host: location.hostname,
          expectedHost,
          h1Count: Array.from(document.querySelectorAll('h1')).filter(visible).length,
          horizontalOverflow: Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0) > document.documentElement.clientWidth + 1,
          brokenResources: Array.from(document.images).filter((img) => img.complete && img.naturalWidth === 0).map((img) => img.currentSrc || img.src),
          duplicateStyles: styleUrls.filter((value, index) => styleUrls.indexOf(value) !== index),
          bodyStylesheets: document.body ? document.body.querySelectorAll('link[rel~="stylesheet"]').length : 0,
          shellCount: document.querySelectorAll('[data-rmc-shell-root="django-admin"]').length,
          sidebarCount: document.querySelectorAll('[data-rmc-admin-sidebar-v3="1"]').length,
          contractVersion: contract?.version || null,
          adminSite: contract?.adminSite || null,
          correctSite: contract?.adminSite === expectedSite,
          rawIconNames: Array.from(document.querySelectorAll('body *')).filter((node) => node.children.length === 0 && /^(menu|close|search|chevron_right|more_vert)$/.test((node.textContent || '').trim())).length,
        };
      }, { expectedHost, expectedSite });
      let drawer = { applicable: width <= 1024, opened: null, closed: null };
      const drawerToggle = page.locator('[data-rmc-admin-drawer-toggle]').first();
      if (width <= 1024 && await drawerToggle.count()) {
        await drawerToggle.click();
        drawer.opened = await drawerToggle.getAttribute('aria-expanded') === 'true';
        await page.keyboard.press('Escape');
        drawer.closed = await drawerToggle.getAttribute('aria-expanded') === 'false';
      }
      const scenarioId = `${surface}-${width}-${theme}`;
      const screenshot = path.join(artifactDir, `${scenarioId}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      const failures = [];
      if (!response || response.status() !== 200) failures.push(`http_${response?.status() || 'none'}`);
      if (metrics.host !== expectedHost) failures.push('hostname_scope');
      if (metrics.h1Count !== 1) failures.push(`visible_h1_${metrics.h1Count}`);
      if (metrics.horizontalOverflow) failures.push('horizontal_overflow');
      if (metrics.brokenResources.length) failures.push('broken_resources');
      if (metrics.duplicateStyles.length) failures.push('duplicate_stylesheets');
      if (metrics.bodyStylesheets) failures.push('stylesheet_in_body');
      if (metrics.shellCount !== 1 || metrics.sidebarCount !== 1) failures.push('duplicate_admin_shell');
      if (metrics.contractVersion !== 3 || !metrics.correctSite) failures.push('wrong_navigation_contract');
      if (metrics.rawIconNames) failures.push('raw_icon_names');
      if (drawer.applicable && drawer.opened !== true) failures.push('mobile_drawer_did_not_open');
      if (drawer.applicable && drawer.closed !== true) failures.push('mobile_drawer_did_not_close');
      rows.push({ scenarioId, traceId: crypto.randomUUID(), surface, width, theme, status: response?.status() || null, screenshot, metrics, drawer, failures, ok: failures.length === 0 });
    }
  }
  return rows;
}

async function auditAdminSidebarBehavior(page, { surface }) {
  const traceId = crypto.randomUUID();
  const mutations = [];
  await page.setViewportSize({ width: 1440, height: 900 });
  await gotoWithRetries(page, '/admin/');
  await page.waitForTimeout(400);
  const startingContract = await page.evaluate(() => {
    try { return JSON.parse(document.querySelector('#rmcAdminNavigationContract')?.textContent || '{}'); } catch (_error) { return {}; }
  });
  if (await page.locator('[data-rmc-admin-pin-current][aria-pressed="true"]').count()) {
    page.once('dialog', (prompt) => prompt.accept());
    await page.locator('[data-rmc-admin-reset]').first().click();
    await page.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 15000 });
  }
  const fetchPreferenceEnvelope = (endpoint) => page.evaluate(async (url) => {
    const response = await fetch(url, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
    let body = {};
    try { body = await response.json(); } catch (_error) { body = {}; }
    return { ok: response.ok, status: response.status, body };
  }, endpoint);
  let observedStartRevision = startingContract.revision || 0;
  const startEnvelope = await fetchPreferenceEnvelope(
    startingContract.endpoint || '/admin/navigation-preferences/'
  );
  if (startEnvelope.ok) {
    observedStartRevision = startEnvelope.body.revision ?? observedStartRevision;
  }
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+K' : 'Control+K');
  const dialog = page.locator('.rmc-admin-command-v3[open], .rmc-admin-command-v3:modal');
  const commandOpened = await dialog.count() > 0;
  if (commandOpened) {
    await page.locator('[data-rmc-admin-command-query]').fill('academic');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Escape');
  }
  const pin = page.locator('[data-rmc-admin-pin-current]').first();
  await pin.click();
  mutations.push('pin');
  await page.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 15000 });
  await page.reload({ waitUntil: 'domcontentloaded' });
  const persistedPin = await page.locator('[data-rmc-admin-pinned-list] li').count() > 0;
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+K' : 'Control+K');
  const anotherPin = page.locator('.rmc-admin-command-v3 button', { hasText: /^Pin$/ }).first();
  if (await anotherPin.count()) {
    await anotherPin.click();
    mutations.push('pin_second');
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 15000 });
  }
  const pinCountBeforeMove = await page.locator('[data-rmc-admin-pinned-list] li').count();
  let reordered = pinCountBeforeMove < 2;
  let undoRestored = false;
  if (pinCountBeforeMove >= 2) {
    const firstBefore = await page.locator('[data-rmc-admin-pinned-list] li a').first().textContent();
    await page.locator('[data-rmc-admin-pinned-list] li').first().getByRole('button', { name: /move pin down/i }).click();
    mutations.push('move_pin');
    await page.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 15000 });
    const firstAfter = await page.locator('[data-rmc-admin-pinned-list] li a').first().textContent();
    reordered = firstBefore !== firstAfter;
    await page.locator('[data-rmc-admin-pinned-list] li').first().getByRole('button', { name: /remove pin/i }).click();
    mutations.push('unpin');
    await page.locator('[data-rmc-admin-undo-action]').click();
    mutations.push('undo');
    await page.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 15000 });
    undoRestored = await page.locator('[data-rmc-admin-pinned-list] li').count() === pinCountBeforeMove;
  }
  await page.context().setOffline(true);
  await page.locator('[data-rmc-admin-focus]').first().click();
  mutations.push('set_focus_offline');
  const queuedOffline = await page.locator('[data-rmc-admin-sync][data-status="offline"]').count() > 0;
  await page.context().setOffline(false);
  await page.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 20000 });
  await page.evaluate(() => {
    window.__rmcNavigationTelemetry = [];
    window.addEventListener('rmc:admin-navigation-telemetry', (event) => window.__rmcNavigationTelemetry.push(event.detail));
  });
  const peer = await page.context().newPage();
  await gotoWithRetries(peer, '/admin/');
  await Promise.all([
    page.locator('[data-rmc-admin-mode]').first().click(),
    peer.locator('[data-rmc-admin-focus]').first().click(),
  ]);
  mutations.push('two_tab_overlap');
  await page.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 20000 });
  await peer.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 20000 });
  await peer.close();
  const conflictRecovered = await page.evaluate(() => {
    const telemetry = window.__rmcNavigationTelemetry || [];
    return telemetry.some((row) => row && row.event === 'conflict') || document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready';
  });
  const reset = page.locator('[data-rmc-admin-reset]').first();
  page.once('dialog', (prompt) => prompt.accept());
  await reset.click();
  mutations.push('reset');
  await page.waitForFunction(() => document.querySelector('[data-rmc-admin-sync]')?.getAttribute('data-status') === 'ready', null, { timeout: 15000 });
  const ending = await fetchPreferenceEnvelope(
    startingContract.endpoint || '/admin/navigation-preferences/'
  );
  const endingBody = ending.ok ? ending.body : {};
  const checks = { commandOpened, persistedPin, reordered, undoRestored, queuedOffline, conflictRecovered, finalSync: ending.ok };
  return {
    scenarioId: `${surface}-sidebar-behavior`,
    traceId,
    host: new URL(page.url()).hostname,
    startingRevision: observedStartRevision,
    mutations,
    endingRevision: endingBody.revision ?? null,
    checks,
    ok: Object.values(checks).every(Boolean),
  };
}

async function probeTenantHealth() {
  return new Promise((resolve) => {
    if (USE_TENANT_SUBDOMAIN) {
      const req = http.request(
        {
          hostname: '127.0.0.1',
          port: PORT,
          path: '/authentication/login/',
          method: 'GET',
          headers: { Host: TENANT_HOST },
          timeout: 8000,
        },
        (res) => {
          res.resume();
          resolve(res.statusCode >= 200 && res.statusCode < 500);
        },
      );
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
      req.end();
      return;
    }
    const probePath = `/t/${TENANT_SLUG}/authentication/login/`;
    const req = http.get(`http://127.0.0.1:${PORT}${probePath}`, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(8000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForTenantHealth(maxAttempts = 60) {
  for (let i = 0; i < maxAttempts; i += 1) {
    if (await probeTenantHealth()) {
      return;
    }
    await sleepMs(1000);
  }
  throw new Error(`tenant abrupt-end: server not healthy at ${TENANT_BASE}`);
}

async function gotoWithRetries(page, url) {
  let lastErr;
  for (let attempt = 1; attempt <= GOTO_RETRIES; attempt++) {
    try {
      return await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: GOTO_TIMEOUT,
      });
    } catch (e) {
      lastErr = e;
      const msg = String(e);
      if (!isInfraOrNonHtmlSkip(msg)) throw e;
      if (attempt === GOTO_RETRIES) throw e;
      await sleepMs(1200 * attempt);
    }
  }
  throw lastErr;
}

function writeLog(hypothesisId, message, data, runId = 'platform-sweep') {
  const line = JSON.stringify({
    sessionId: SESSION,
    hypothesisId,
    message,
    data,
    timestamp: Date.now(),
    runId,
    location: 'verify_platform_abrupt_end_sweep.mjs',
  });
  fs.appendFileSync(LOG, line + '\n');
}

/** Single browser callback — Playwright only serializes one function per evaluate(). */
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
  function resolveMain(sel) {
    const roots = sel
      ? [document.querySelector(sel)]
      : [
          document.querySelector('#cp-main-content'),
          document.querySelector('#main-content'),
          document.querySelector('main[role="main"]'),
          document.querySelector('main'),
        ];
    return findScrollable(roots.find(Boolean) || null);
  }
  function countStranded() {
    let stranded = 0;
    document.querySelectorAll('.rmc-reveal').forEach((el) => {
      if (el.classList.contains('is-revealed')) return;
      if (parseFloat(getComputedStyle(el).opacity) < 0.05) stranded += 1;
    });
    return stranded;
  }

  const main = resolveMain(scrollRootSel);
  const body = document.body;
  const bodyOY = body ? getComputedStyle(body).overflowY : '';
  const before = {
    path: location.pathname,
    armed: document.documentElement.getAttribute('data-rmc-reveal-armed'),
    mainId: main?.id || null,
    mainMaxH: main ? getComputedStyle(main).maxHeight : null,
    mainScrollH: main?.scrollHeight ?? null,
    mainClientH: main?.clientHeight ?? null,
    bodyOY,
    revealTotal: document.querySelectorAll('.rmc-reveal').length,
    strandedBefore: countStranded(),
    badMaxHeight:
      main &&
      /calc\s*\(\s*100vh\s*-\s*56px\s*\)/i.test(getComputedStyle(main).maxHeight),
    canScroll: !!(main && main.scrollHeight > main.clientHeight + 2),
  };

  if (before.canScroll) {
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
  if (before.badMaxHeight) failures.push('bad_max_height_56px');
  if (trapped) failures.push('body_scroll_trapped');
  if (main && main.scrollHeight > main.clientHeight + 100 && strandedAfter > 0) {
    failures.push(`scrollable_but_stranded_${strandedAfter}`);
  }

  return {
    ...before,
    strandedAfter,
    mainScrollTop: main?.scrollTop ?? null,
    failures,
    ok: failures.length === 0,
  };
}

function finalizeTenantSweepRow(s, audit) {
  if (
    isAuthEscapePath(audit.path) &&
    !isAuthEscapePath(s.url) &&
    !isAuthenticationRootRoute(s.url)
  ) {
    return {
      ...s,
      ...audit,
      ok: false,
      failures: ['auth_escape'],
    };
  }
  return { ...s, ...audit };
}

async function loginTenant(page, opts = {}) {
  const tenantUser =
    opts.username ||
    process.env.TENANT_SWEEP_USERNAME ||
    process.env.E2E_TENANT_USER ||
    'demo.admin';
  const tenantPassword =
    opts.password ||
    process.env.TENANT_SWEEP_PASSWORD ||
    process.env.E2E_TENANT_PASSWORD ||
    'Test1234';
  await loginTenantMfa(page, { username: tenantUser, password: tenantPassword });
}

async function assertTenantSessionReady(page) {
  let pathname = '';
  try {
    pathname = new URL(page.url()).pathname;
  } catch (_e) {
    throw new Error('tenant login incomplete: invalid page URL after login');
  }
  if (/\/authentication\/(login|mfa\/verify)/i.test(pathname)) {
    throw new Error(`tenant login incomplete: stuck on ${pathname}`);
  }
}

function isAuthEscapePath(pathname) {
  return /\/authentication\/(login|mfa\/verify)/i.test(String(pathname || ''));
}

function isAuthenticationRootRoute(url) {
  return /^\/authentication\/?$/i.test(String(url || ''));
}

const TENANT_SWEEP_USER =
  process.env.TENANT_SWEEP_USERNAME || process.env.E2E_TENANT_USER || 'demo.admin';
const TENANT_SWEEP_PASSWORD =
  process.env.TENANT_SWEEP_PASSWORD || process.env.E2E_TENANT_PASSWORD || 'Test1234';

/** @type {Array<[RegExp, string]>} */
const ROUTE_USER_MAP = [
  [/^\/portal\/parent(?:\/|$)/i, 'demo.parent'],
  [/^\/portal\/teacher(?:\/|$)/i, 'demo.teacher'],
  [/^\/portal\/student-portal(?:\/|$)/i, 'demo.student'],
];

function resolveUserForRoute(url) {
  const path = String(url || '');
  for (const [pattern, username] of ROUTE_USER_MAP) {
    if (pattern.test(path)) {
      return username;
    }
  }
  return TENANT_SWEEP_USER;
}

async function ensureTenantUser(page, username) {
  await page.context().clearCookies();
  await loginTenant(page, { username, password: TENANT_SWEEP_PASSWORD });
  await assertTenantSessionReady(page);
}

async function main() {
  if (fs.existsSync(LOG)) fs.unlinkSync(LOG);

  const artifactDir = path.resolve(process.env.VISUAL_QA_ARTIFACT_DIR || 'artifacts/admin-platform-proof');
  fs.mkdirSync(artifactDir, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    args: chromiumLaunchArgs(HOST_RULES),
  });
  const browserVersion = browser.version();

  const results = [];
  const viewportThemeMatrix = [];
  const scenarios = [];
  const resourceErrors = [];
  let failures = 0;
  let skipped = 0;

  // --- Manager / admin surfaces ---
  const managerSurfaces = SURFACES.filter((x) => x.surface === 'manager');
  if (managerSurfaces.length) {
  const mgrCtx = await browser.newContext({
    baseURL: BASE,
    viewport: SWEEP_VIEWPORT,
    storageState: fs.existsSync(AUTH) ? AUTH : undefined,
  });
  const mgrPage = await mgrCtx.newPage();
  mgrPage.on('requestfailed', (request) => resourceErrors.push({ surface: 'manager', type: 'requestfailed', url: request.url(), error: request.failure()?.errorText || 'failed' }));
  mgrPage.on('pageerror', (error) => resourceErrors.push({ surface: 'manager', type: 'pageerror', error: String(error) }));
  if (!fs.existsSync(AUTH)) {
    await loginManager(mgrPage);
  }

  const mgrPages = [mgrPage];
  for (let index = 1; index < ROUTE_CONCURRENCY; index += 1) {
    const workerPage = await mgrCtx.newPage();
    workerPage.on('requestfailed', (request) => resourceErrors.push({ surface: 'manager', type: 'requestfailed', url: request.url(), error: request.failure()?.errorText || 'failed' }));
    workerPage.on('pageerror', (error) => resourceErrors.push({ surface: 'manager', type: 'pageerror', error: String(error) }));
    mgrPages.push(workerPage);
  }
  let managerCursor = 0;
  await Promise.all(mgrPages.map(async (workerPage) => {
    while (managerCursor < managerSurfaces.length) {
      const cursor = managerCursor;
      managerCursor += 1;
      const s = managerSurfaces[cursor];
    try {
      const resp = await gotoWithRetries(workerPage, s.url);
      if (resp && resp.status() >= 400) {
        if (resp.status() >= 500 && s.url.startsWith('/admin/')) {
          failures += 1;
          const row = {
            ...s,
            ok: false,
            failures: [`http_${resp.status()}`],
            error: `HTTP ${resp.status()}`,
          };
          results.push(row);
          writeLog('SWEEP', 'FAIL', row);
          continue;
        }
        skipped += 1;
        results.push({ ...s, ok: true, skipped: `http_${resp.status()}` });
        continue;
      }
      await workerPage.waitForTimeout(ROUTE_SETTLE_MS);
      let audit = await workerPage.evaluate(sweepPageInBrowser, s.scrollRoot || null);
      if (/\/authentication\/(login|mfa\/verify)/.test(audit.path)) {
        failures += 1;
        const row = { ...s, ...audit, ok: false, failures: ['auth_escape'] };
        results.push(row);
        writeLog('SWEEP', 'FAIL', row);
        continue;
      }
      await workerPage.waitForTimeout(ROUTE_STABILITY_MS);
      audit = await workerPage.evaluate(sweepPageInBrowser, s.scrollRoot || null);
      const requestedAdmin = s.url.startsWith('/admin/');
      const landedAdmin = audit.path && String(audit.path).startsWith('/admin/');
      if (requestedAdmin && !landedAdmin) {
        skipped += 1;
        const row = {
          ...s,
          ...audit,
          ok: true,
          skipped: 'redirect_escape',
        };
        results.push(row);
        writeLog('SWEEP', 'skip_redirect_escape', row);
        continue;
      }
      const row = { ...s, ...audit };
      results.push(row);
      writeLog('SWEEP', row.ok ? 'pass' : 'FAIL', row);
      if (!row.ok) failures += 1;
    } catch (e) {
      const err = String(e);
      if (isInfraOrNonHtmlSkip(err)) {
        skipped += 1;
        const row = { ...s, ok: true, skipped: 'infra_or_redirect', error: err };
        results.push(row);
        writeLog('SWEEP', 'skip', row);
      } else {
        failures += 1;
        const row = { ...s, ok: false, failures: ['exception'], error: err };
        results.push(row);
        writeLog('SWEEP', 'FAIL', row);
      }
    }
    }
  }));
  await Promise.all(mgrPages.slice(1).map((page) => page.close()));
  if (SWEEP_TIER === 'admin_changelist') {
    viewportThemeMatrix.push(...await auditAdminViewportMatrix(mgrPage, {
      surface: 'manager', expectedHost: HOST, expectedSite: 'admin', artifactDir,
    }));
    scenarios.push(await auditAdminSidebarBehavior(mgrPage, { surface: 'manager' }));
  }
  await mgrCtx.close();
  }

  // --- Tenant surfaces (separate host + inner paths when USE_TENANT_SUBDOMAIN=1) ---
  const tenHostRules =
    process.env.PLAYWRIGHT_TENANT_HOST_RULES ||
    `MAP ${TENANT_HOST} 127.0.0.1,MAP *.runmycampus.com 127.0.0.1`;
  const tenBrowser = await chromium.launch({
    headless: true,
    args: chromiumLaunchArgs(tenHostRules),
  });
  const tenCtx = await tenBrowser.newContext({
    baseURL: TENANT_BASE,
    viewport: SWEEP_VIEWPORT,
  });
  const tenPage = await tenCtx.newPage();
  tenPage.on('requestfailed', (request) => resourceErrors.push({ surface: 'tenant', type: 'requestfailed', url: request.url(), error: request.failure()?.errorText || 'failed' }));
  tenPage.on('pageerror', (error) => resourceErrors.push({ surface: 'tenant', type: 'pageerror', error: String(error) }));
  try {
    await ensureTenantUser(tenPage, TENANT_SWEEP_USER);
    const tenantSurfaces = SURFACES.filter((x) => x.surface === 'tenant');
    const tenPages = [tenPage];
    for (let index = 1; index < ROUTE_CONCURRENCY; index += 1) {
      const workerPage = await tenCtx.newPage();
      workerPage.on('requestfailed', (request) => resourceErrors.push({ surface: 'tenant', type: 'requestfailed', url: request.url(), error: request.failure()?.errorText || 'failed' }));
      workerPage.on('pageerror', (error) => resourceErrors.push({ surface: 'tenant', type: 'pageerror', error: String(error) }));
      tenPages.push(workerPage);
    }
    let tenantCursor = 0;
    await Promise.all(tenPages.map(async (workerPage) => {
      while (tenantCursor < tenantSurfaces.length) {
        const cursor = tenantCursor;
        tenantCursor += 1;
        const s = tenantSurfaces[cursor];
      try {
        const routeUser = resolveUserForRoute(s.url);
        if (routeUser !== TENANT_SWEEP_USER) {
          failures += 1;
          const row = { ...s, ok: false, failures: ['mixed_role_route_in_admin_sweep'] };
          results.push(row);
          writeLog('SWEEP', 'FAIL', row);
          continue;
        }
        const response = await gotoWithRetries(workerPage, s.url);
        if (!response || response.status() !== 200) {
          failures += 1;
          const row = { ...s, ok: false, status: response?.status() || null, failures: [`http_${response?.status() || 'none'}`] };
          results.push(row);
          writeLog('SWEEP', 'FAIL', row);
          continue;
        }
        if (!USE_TENANT_SUBDOMAIN) {
          await ensurePathTenantHost(workerPage);
        }
        await workerPage.waitForTimeout(ROUTE_SETTLE_MS);
        let audit = await workerPage.evaluate(
          sweepPageInBrowser,
          s.scrollRoot || '#main-content'
        );
        await workerPage.waitForTimeout(ROUTE_STABILITY_MS);
        audit = await workerPage.evaluate(
          sweepPageInBrowser,
          s.scrollRoot || '#main-content'
        );
        if (isAuthEscapePath(audit.path) && !isAuthEscapePath(s.url)) {
          failures += 1;
          const row = finalizeTenantSweepRow(s, audit);
          results.push(row);
          writeLog('SWEEP', 'FAIL', row);
          continue;
        }
        if (
          isAuthEscapePath(audit.path) &&
          !isAuthEscapePath(s.url) &&
          !isAuthenticationRootRoute(s.url)
        ) {
          failures += 1;
          const row = finalizeTenantSweepRow(s, audit);
          results.push(row);
          writeLog('SWEEP', 'FAIL', row);
          continue;
        }
        const row = finalizeTenantSweepRow(s, audit);
        results.push(row);
        writeLog('SWEEP', row.ok ? 'pass' : 'FAIL', row);
        if (!row.ok) failures += 1;
      } catch (e) {
        const err = String(e);
        if (isInfraOrNonHtmlSkip(err)) {
          await waitForTenantHealth(30).catch(() => null);
          try {
            await gotoWithRetries(workerPage, s.url);
            if (!USE_TENANT_SUBDOMAIN) {
              await ensurePathTenantHost(workerPage);
            }
            await workerPage.waitForTimeout(ROUTE_SETTLE_MS);
            const audit = await workerPage.evaluate(
              sweepPageInBrowser,
              s.scrollRoot || '#main-content'
            );
            const row = finalizeTenantSweepRow(s, audit);
            results.push(row);
            writeLog('SWEEP', row.ok ? 'pass' : 'FAIL', row);
            if (!row.ok) failures += 1;
            continue;
          } catch (retryErr) {
            /* fall through to infra skip */
          }
        }
        if (isInfraOrNonHtmlSkip(err)) {
          skipped += 1;
          const row = { ...s, ok: true, skipped: 'infra_or_redirect', error: err };
          results.push(row);
          writeLog('SWEEP', 'skip', row);
        } else {
          failures += 1;
          const row = { ...s, ok: false, failures: ['exception'], error: err };
          results.push(row);
          writeLog('SWEEP', 'FAIL', row);
        }
      }
      }
    }));
    await Promise.all(tenPages.slice(1).map((page) => page.close()));
    if (SWEEP_TIER === 'admin_changelist') {
      viewportThemeMatrix.push(...await auditAdminViewportMatrix(tenPage, {
        surface: 'tenant', expectedHost: TENANT_HOST, expectedSite: 'tenant_admin', artifactDir,
      }));
      scenarios.push(await auditAdminSidebarBehavior(tenPage, { surface: 'tenant' }));
    }
  } catch (e) {
    writeLog('SWEEP', 'tenant_skipped', { error: String(e) });
    skipped += SURFACES.filter((x) => x.surface === 'tenant').length;
  }
  await tenCtx.close();
  await tenBrowser.close();
  await browser.close();

  const failed = results.filter(
    (r) =>
      r.ok === false &&
      !(r.failures || []).every(
        (f) => f === 'exception' && isInfraOrNonHtmlSkip(r.error)
      )
  );
  const layoutFailed = failed.filter((r) =>
    (r.failures || []).some((f) => f !== 'exception')
  );
  const proofFailed = [
    ...viewportThemeMatrix.filter((row) => !row.ok),
    ...scenarios.filter((row) => !row.ok),
  ];
  const managerPlanned = SURFACES.filter((x) => x.surface === 'manager').length;
  const tenantPlanned = SURFACES.filter((x) => x.surface === 'tenant').length;
  const managerTested = results.filter((r) => r.surface === 'manager').length;
  const tenantTested = results.filter((r) => r.surface === 'tenant').length;
  const infraSkipped = results.filter((r) => r.skipped).length;
  const layoutProven = results.filter(
    (r) =>
      r.surface === 'tenant' &&
      r.ok === true &&
      !r.skipped &&
      !isAuthEscapePath(r.path)
  ).length;
  const maxInfraSkip = parseInt(
    process.env.TENANT_SWEEP_MAX_INFRA_SKIP || '0',
    10
  );
  const summary = {
    generatedAt: new Date().toISOString(),
    sweepTier: process.env.SWEEP_TIER || 'operator',
    managerBase: BASE,
    tenantBase: TENANT_BASE,
    useTenantSubdomain: USE_TENANT_SUBDOMAIN,
    managerPlanned,
    tenantPlanned,
    managerTested,
    tenantTested,
    layoutProven,
    resultsCount: results.length,
    passed: results.filter((r) => r.ok).length,
    failed: layoutFailed.length,
    skipped,
    infraSkipped,
    proofFailed: proofFailed.length,
    failedUrls: layoutFailed.map((r) => ({
      url: r.url,
      failures: r.failures,
      error: r.error,
    })),
  };
  const generatedAt = new Date();
  const buildLockPath = path.join(process.cwd(), 'var/admin-approval-build-lock.json');
  const routeManifestHashes = {
    operator: sha256File(ROUTES_JSON),
    tenant: sha256File(TENANT_ADMIN_ROUTES_JSON),
  };
  const sealedSourceFiles = [
    'apps/siteconfig/admin_navigation_contracts.py',
    'apps/siteconfig/admin_navigation_preferences.py',
    'config/admin.py',
    'templates/admin/base.html',
    'templates/admin/sidebar_v3_body.html',
    'static/css/rmc-admin-sidebar-v3.css',
    'static/js/rmc-admin-sidebar-v3.js',
    'static/js/service-worker.js',
    'var/admin-approval-build-lock.json',
  ];
  const sourceFileHashes = Object.fromEntries(
    sealedSourceFiles.map((file) => [file, sha256File(path.join(process.cwd(), file))])
  );
  const buildLock = fs.existsSync(buildLockPath)
    ? JSON.parse(fs.readFileSync(buildLockPath, 'utf8'))
    : null;
  const evidence = {
    schemaVersion: 3,
    generatedAt: generatedAt.toISOString(),
    expiresAt: new Date(generatedAt.getTime() + 24 * 60 * 60 * 1000).toISOString(),
    sweepTier: process.env.SWEEP_TIER || 'operator',
    evidenceSource: 'playwright_real_host_admin_v3',
    proxyEvidence: false,
    realHostRouting: true,
    gitSha: gitValue(['rev-parse', 'HEAD']),
    sourceTreeDigest: crypto.createHash('sha256').update(gitValue(['status', '--porcelain'], '') + gitValue(['diff', '--binary'], '')).digest('hex'),
    browser: { name: 'chromium', version: browserVersion },
    hostMatrix: [HOST, TENANT_HOST],
    routeManifestHashes,
    sourceFileHashes,
    buildLock,
    viewportThemeMatrix,
    scenarios,
    resourceErrors,
    ...summary,
    results,
  };
  const auditPath = path.join(
    process.cwd(),
    'docs/generated/admin_playwright_sweep_audit.json'
  );
  fs.mkdirSync(path.dirname(auditPath), { recursive: true });
  fs.writeFileSync(
    auditPath,
    JSON.stringify(evidence, null, 2) + '\n'
  );
  if (SWEEP_TIER === 'tenant') {
    const writeArtifact =
      (process.env.TENANT_SWEEP_WRITE_ARTIFACT || '1').toLowerCase() !== '0';
    if (writeArtifact) {
      const tenantArtifact = path.join(
        process.cwd(),
        'var/tenant-abrupt-end-sweep.json'
      );
      fs.mkdirSync(path.dirname(tenantArtifact), { recursive: true });
      fs.writeFileSync(
        tenantArtifact,
        JSON.stringify({ ...summary, results }, null, 2) + '\n'
      );
      console.log(`Wrote ${tenantArtifact}`);
    }
  }

  writeLog('SUMMARY', 'platform abrupt-end sweep', summary);
  console.log(JSON.stringify(summary, null, 2));
  console.log(`Wrote ${auditPath}`);
  if (SWEEP_TIER === 'tenant') {
    if (tenantTested < tenantPlanned) {
      console.error(
        `tenant abrupt-end: tenantTested=${tenantTested} < tenantPlanned=${tenantPlanned}`
      );
      process.exit(1);
    }
    if (layoutProven < tenantPlanned) {
      console.error(
        `tenant abrupt-end: layoutProven=${layoutProven} < tenantPlanned=${tenantPlanned}`
      );
      process.exit(1);
    }
    if (infraSkipped > maxInfraSkip) {
      console.error(
        `tenant abrupt-end: infraSkipped=${infraSkipped} > max ${maxInfraSkip}`
      );
      process.exit(1);
    }
  }
  if (layoutFailed.length) {
    console.error('\nLayout failures (abrupt end / stranded reveal):');
    for (const f of layoutFailed) {
      console.error(`  ${f.url} → ${(f.failures || []).join(', ')}`);
    }
    process.exit(1);
  }
  if (proofFailed.length) {
    console.error(`Admin v3 browser proof failures: ${proofFailed.map((row) => row.scenarioId).join(', ')}`);
    process.exit(1);
  }
  if (SWEEP_TIER === 'tenant') {
    console.log('TENANT_ABRUPT_END_SWEEP_PASS');
  }
  process.exit(0);
}

main().catch((e) => {
  writeLog('SUMMARY', 'fatal', { error: String(e) });
  console.error(e);
  process.exit(1);
});
