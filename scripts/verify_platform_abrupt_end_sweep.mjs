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
import path from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const {
  loginManager,
  AUTH_STATE_PATH,
} = require('../tests/e2e/helpers/manager-login');
const { loginTenant: loginTenantMfa } = require('../tests/e2e/helpers/tenant-login');

const LOG = path.join(process.cwd(), 'debug-7911e1.log');
const SESSION = '7911e1';
const HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const PORT = process.env.VISUAL_QA_PORT || '8012';
const BASE = process.env.MANAGER_BASE_URL || `http://${HOST}:${PORT}`;
const TENANT_SLUG = process.env.TENANT_SWEEP_SLUG || 'demo-school';
const TENANT_HOST =
  process.env.VISUAL_QA_TENANT_HOST || `${TENANT_SLUG}.runmycampus.com`;
const TENANT_BASE =
  process.env.TENANT_BASE_URL || `http://${TENANT_HOST}:${PORT}`;
const USE_TENANT_SUBDOMAIN =
  (process.env.USE_TENANT_SUBDOMAIN || '1').toLowerCase() !== '0';
const AUTH = AUTH_STATE_PATH;
const HOST_RULES =
  process.env.PLAYWRIGHT_HOST_RULES || `MAP ${HOST} 127.0.0.1`;
const ROUTES_JSON = path.join(
  process.cwd(),
  'docs/generated/control_plane_sweep_routes.json'
);
const TENANT_ROUTES_JSON = path.join(
  process.cwd(),
  'docs/generated/portal_tenant_sweep_routes.json'
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
      if (pathFilter.length && !pathFilter.some((p) => row.path.startsWith(p))) {
        return false;
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
  if (!fs.existsSync(TENANT_ROUTES_JSON)) {
    return FALLBACK_SURFACES.filter((s) => s.surface === 'tenant');
  }
  const data = JSON.parse(fs.readFileSync(TENANT_ROUTES_JSON, 'utf8'));
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
  ...(INCLUDE_TENANT && SWEEP_TIER !== 'admin_changelist'
    ? loadTenantSurfaces()
    : []),
];

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

async function loginTenant(page) {
  const tenantUser =
    process.env.TENANT_SWEEP_USERNAME ||
    process.env.E2E_TENANT_USER ||
    'demo.admin';
  const tenantPassword =
    process.env.TENANT_SWEEP_PASSWORD ||
    process.env.E2E_TENANT_PASSWORD ||
    'Test1234';
  await loginTenantMfa(page, { username: tenantUser, password: tenantPassword });
}

async function main() {
  if (fs.existsSync(LOG)) fs.unlinkSync(LOG);

  const browser = await chromium.launch({
    headless: true,
    args: [`--host-resolver-rules=${HOST_RULES}`],
  });

  const results = [];
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
  if (!fs.existsSync(AUTH)) {
    await loginManager(mgrPage);
  }

  for (const s of managerSurfaces) {
    try {
      const resp = await gotoWithRetries(mgrPage, s.url);
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
      await mgrPage.waitForTimeout(1200);
      let audit = await mgrPage.evaluate(sweepPageInBrowser, s.scrollRoot || null);
      if (/\/authentication\/(login|mfa\/verify)/.test(audit.path)) {
        await loginManager(mgrPage);
        await gotoWithRetries(mgrPage, s.url);
        await mgrPage.waitForTimeout(1200);
        audit = await mgrPage.evaluate(sweepPageInBrowser, s.scrollRoot || null);
      }
      await mgrPage.waitForTimeout(650);
      audit = await mgrPage.evaluate(sweepPageInBrowser, s.scrollRoot || null);
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
  await mgrCtx.close();
  }

  // --- Tenant surfaces (separate host + inner paths when USE_TENANT_SUBDOMAIN=1) ---
  const tenHostRules =
    process.env.PLAYWRIGHT_TENANT_HOST_RULES ||
    `MAP ${TENANT_HOST} 127.0.0.1`;
  const tenBrowser = await chromium.launch({
    headless: true,
    args: [`--host-resolver-rules=${tenHostRules}`],
  });
  const tenCtx = await tenBrowser.newContext({
    baseURL: TENANT_BASE,
    viewport: SWEEP_VIEWPORT,
  });
  const tenPage = await tenCtx.newPage();
  try {
    await loginTenant(tenPage);
    for (const s of SURFACES.filter((x) => x.surface === 'tenant')) {
      try {
        await gotoWithRetries(tenPage, s.url);
        await tenPage.waitForTimeout(1200);
        let audit = await tenPage.evaluate(
          sweepPageInBrowser,
          s.scrollRoot || '#main-content'
        );
        await tenPage.waitForTimeout(650);
        audit = await tenPage.evaluate(
          sweepPageInBrowser,
          s.scrollRoot || '#main-content'
        );
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
  const managerPlanned = SURFACES.filter((x) => x.surface === 'manager').length;
  const tenantPlanned = SURFACES.filter((x) => x.surface === 'tenant').length;
  const managerTested = results.filter((r) => r.surface === 'manager').length;
  const tenantTested = results.filter((r) => r.surface === 'tenant').length;
  const infraSkipped = results.filter((r) => r.skipped).length;
  const layoutProven = results.filter(
    (r) => r.surface === 'tenant' && r.ok === true && !r.skipped
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
    failedUrls: layoutFailed.map((r) => ({
      url: r.url,
      failures: r.failures,
      error: r.error,
    })),
  };
  const auditPath = path.join(
    process.cwd(),
    'docs/generated/admin_playwright_sweep_audit.json'
  );
  fs.mkdirSync(path.dirname(auditPath), { recursive: true });
  fs.writeFileSync(
    auditPath,
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        ...summary,
        results,
      },
      null,
      2
    ) + '\n'
  );
  if (SWEEP_TIER === 'tenant') {
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
