#!/usr/bin/env node
/**
 * MAX parity fold proof — closes the live Playwright residual for Waves 1–5.
 *
 * Boots Django (or reuses VISUAL_QA_PORT), logs into manager + tenant, visits
 * Mission/Money twins, asserts masthead / work-root / role-tab URL state /
 * sparklines / fold chrome bands, writes screenshots + JSON summary.
 *
 * Usage:
 *   node scripts/verify_max_parity_fold_playwright.mjs
 *   npm run test:e2e:max-parity-fold
 *
 * Env:
 *   VISUAL_QA_PORT (default 8012)
 *   MAX_FOLD_REUSE_SERVER=1  — skip boot; expect server already up
 *   DB_FILE — optional; default var/max_parity_fold.sqlite3 seeded from p0 live DB
 *   RMC_E2E_SKIP_MIGRATE=1 — skip migrate after seed (not recommended)
 */
import { spawn, spawnSync, execFileSync } from 'child_process';
import fs from 'fs';
import http from 'http';
import net from 'net';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(__dirname, '..');
const port = String(process.env.VISUAL_QA_PORT || '8012');
// Prefer manager.localhost — Chromium resolves *.localhost → 127.0.0.1 without host-resolver
// (Windows often breaks MAP for manager.runmycampus.com via HSTS / CONNECTION_REFUSED).
const managerHost =
  process.env.VISUAL_QA_MANAGER_HOST || 'manager.localhost';
const tenantSlug = process.env.TENANT_SLUG || 'demo-school';

// Pin env BEFORE requiring login helpers (they capture port/base at module load).
process.env.VISUAL_QA_PORT = port;
process.env.VISUAL_QA_TENANT_PHASE_PORT = port;
process.env.VISUAL_QA_MANAGER_HOST = managerHost;
process.env.MANAGER_BASE_URL = `http://${managerHost}:${port}`;
process.env.TENANT_SLUG = tenantSlug;
// Path /t/<slug>/ permanently redirects to the tenant subdomain; Chromium needs MAP
// for *.runmycampus.com. Prefer subdomain transport and never navigate to 127.0.0.1
// after MAP (Windows Chromium then fails literal 127.0.0.1 with ERR_NAME_NOT_RESOLVED).
process.env.TENANT_E2E_SUBDOMAIN = process.env.TENANT_E2E_SUBDOMAIN || '1';
process.env.VISUAL_QA_TENANT_HOST =
  process.env.VISUAL_QA_TENANT_HOST || `${tenantSlug}.runmycampus.com`;
process.env.TENANT_E2E_BASE_URL =
  process.env.TENANT_E2E_BASE_URL ||
  `http://${process.env.VISUAL_QA_TENANT_HOST}:${port}`;
process.env.TENANT_BASE_URL = process.env.TENANT_E2E_BASE_URL;
process.env.RMC_E2E_BYPASS_MFA = process.env.RMC_E2E_BYPASS_MFA || '1';
process.env.LOGIN_POW_ENABLED = process.env.LOGIN_POW_ENABLED || '0';

const require = createRequire(import.meta.url);
const { loginManager } = require('../tests/e2e/helpers/manager-login');
const { loginTenant } = require('../tests/e2e/helpers/tenant-login');

const artifactDir = path.join(repo, 'artifacts', 'max-parity-fold');
const summaryPath = path.join(artifactDir, 'fold-proof-summary.json');
const serverLog = path.join(artifactDir, 'runserver.log');
const reuseServer = process.env.MAX_FOLD_REUSE_SERVER === '1';
const gateDb =
  process.env.MAX_FOLD_GATE_DB ||
  path.join(repo, 'db_playwright_p0_e2e_live.sqlite3');
const dbFile =
  process.env.DB_FILE || path.join(repo, 'var', 'max_parity_fold.sqlite3');

const HOST_RESOLVER_RULES =
  process.env.PLAYWRIGHT_MAX_FOLD_HOST_RULES ||
  // manager.localhost resolves natively in Chromium; tenant subdomain needs MAP.
  // Do not MAP anything onto rules that break later navigations to 127.0.0.1 —
  // this harness uses only manager.localhost + <slug>.runmycampus.com.
  `MAP ${tenantSlug}.runmycampus.com 127.0.0.1`;

function chromiumLaunchArgs() {
  const args = [
    '--proxy-server=direct://',
    '--proxy-bypass-list=*',
    '--disable-features=HttpsUpgrades,HttpsFirstMode,HttpsFirstBalancedModeAutoEnable,HttpsOnlyMode',
  ];
  if (HOST_RESOLVER_RULES.trim()) {
    args.unshift(`--host-resolver-rules=${HOST_RESOLVER_RULES}`);
  }
  return args;
}

function managerPageUrl(pathPart) {
  const p = pathPart.startsWith('/') ? pathPart : `/${pathPart}`;
  return `http://${managerHost}:${port}${p}`;
}

function resolvePython() {
  return (
    process.env.VISUAL_QA_PYTHON ||
    process.env.PYTHON ||
    (process.platform === 'win32' ? 'python' : 'python3')
  );
}

const py = resolvePython();

function httpOk(url, timeoutMs = 2000) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

/** Prefer a cheap probe — login HTML is too heavy for single-threaded runserver polls. */
function readinessUrl() {
  return (
    process.env.MAX_FOLD_READY_URL ||
    `http://127.0.0.1:${port}/observability/health/`
  );
}

function tcpListening(host, portNum, timeoutMs = 1500) {
  return new Promise((resolve) => {
    const sock = net.connect({ host, port: portNum }, () => {
      sock.end();
      resolve(true);
    });
    sock.setTimeout(timeoutMs);
    sock.on('timeout', () => {
      sock.destroy();
      resolve(false);
    });
    sock.on('error', () => resolve(false));
  });
}

function seedDbIfNeeded() {
  fs.mkdirSync(path.dirname(dbFile), { recursive: true });
  if (fs.existsSync(dbFile) && fs.statSync(dbFile).size > 1_000_000) {
    console.log(`=== max-fold: reuse DB ${dbFile} ===`);
    return;
  }
  if (!fs.existsSync(gateDb)) {
    console.error(`max-fold: missing gate DB ${gateDb}`);
    process.exit(2);
  }
  console.log(`=== max-fold: seed DB from ${path.basename(gateDb)} ===`);
  const script = `
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=60)
dst_conn = sqlite3.connect(dst, timeout=60)
src_conn.backup(dst_conn)
dst_conn.commit()
dst_conn.close()
src_conn.close()
`;
  for (const suffix of ['', '-wal', '-shm']) {
    const p = suffix ? `${dbFile}${suffix}` : dbFile;
    if (fs.existsSync(p)) fs.unlinkSync(p);
  }
  execFileSync(py, ['-c', script, gateDb, dbFile], { cwd: repo, stdio: 'inherit' });
}

const baseEnv = {
  ...process.env,
  DB_FILE: dbFile,
  DJANGO_SQLITE_TIMEOUT: process.env.DJANGO_SQLITE_TIMEOUT || '90',
  REDIS_URL: '',
  RMC_FORCE_DB_SESSIONS: '1',
  SECURE_SSL_REDIRECT: '0',
  // DEBUG=1 required for RMC_E2E_BYPASS_MFA (see apps/accounts/e2e_mfa_bypass.py).
  DEBUG: process.env.DEBUG ?? '1',
  // Keep DEBUG=1 for MFA bypass but silence SQL flood (settings.py django.db logger).
  DB_LOG_LEVEL: process.env.DB_LOG_LEVEL || 'WARNING',
  DJANGO_LOG_LEVEL: process.env.DJANGO_LOG_LEVEL || 'WARNING',
  DJANGO_LOG_LEVEL: process.env.DJANGO_LOG_LEVEL || 'WARNING',
  CSRF_COOKIE_SECURE: '0',
  SESSION_COOKIE_SECURE: '0',
  RMC_DEPLOYMENT_PROFILE: 'online',
  OBSERVABILITY_METRICS_BACKEND: 'noop',
  // Skip Ollama probe during e2e — login page was blocking single-threaded runserver.
  OLLAMA_BASE_URL: process.env.OLLAMA_BASE_URL || '',
  RMC_SKIP_OLLAMA_AUTODISCOVER: process.env.RMC_SKIP_OLLAMA_AUTODISCOVER || '1',
  ALLOWED_HOSTS:
    process.env.ALLOWED_HOSTS ||
    '127.0.0.1,localhost,.localhost,testserver,runmycampus.com,.runmycampus.com,manager.localhost,manager.runmycampus.com,demo-school.runmycampus.com',
  MULTI_TENANT_BASE_DOMAIN: process.env.MULTI_TENANT_BASE_DOMAIN || 'runmycampus.com',
  VISUAL_QA_PORT: port,
  VISUAL_QA_TENANT_PHASE_PORT: port,
  TENANT_SLUG: tenantSlug,
  LOGIN_POW_ENABLED: '0',
  RMC_E2E_BYPASS_MFA: process.env.RMC_E2E_BYPASS_MFA || '1',
  PYTHONUTF8: '1',
  PYTHONUNBUFFERED: '1',
};

let server = null;
let serverLogFd = null;

function stopServer() {
  if (!server?.pid) return;
  try {
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(server.pid), '/t', '/f'], {
        stdio: 'ignore',
      });
    } else {
      process.kill(server.pid);
    }
  } catch (_e) {
    /* ignore */
  }
  server = null;
  if (serverLogFd != null) {
    try {
      fs.closeSync(serverLogFd);
    } catch (_e) {
      /* ignore */
    }
    serverLogFd = null;
  }
}

async function waitForServer(attempts = 120) {
  const ready = readinessUrl();
  for (let i = 0; i < attempts; i++) {
    if (await tcpListening('127.0.0.1', Number(port))) {
      // Prefer a cheap health probe; fall back to any response on /
      if (await httpOk(ready, 20000)) {
        // Brief settle — first request after migrate/boot can still be heavy.
        await new Promise((r) => setTimeout(r, 1500));
        return true;
      }
      if (await httpOk(`http://127.0.0.1:${port}/`, 20000)) {
        await new Promise((r) => setTimeout(r, 1500));
        return true;
      }
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

async function startServerIfNeeded() {
  // Only reuse when explicitly requested — an orphan on :port often lacks
  // DEBUG/RMC_E2E_BYPASS_MFA and will trap manager login on MFA verify.
  if (reuseServer) {
    if (await httpOk(`http://127.0.0.1:${port}/`, 15000)) {
      console.log(`=== max-fold: reuse server on :${port} ===`);
      return;
    }
    console.error(`max-fold: MAX_FOLD_REUSE_SERVER=1 but nothing healthy on :${port}`);
    process.exit(1);
  }
  if (await tcpListening('127.0.0.1', Number(port))) {
    console.log(`=== max-fold: freeing occupied :${port} ===`);
    try {
      if (process.platform === 'win32') {
        const out = spawnSync(
          'powershell.exe',
          [
            '-NoProfile',
            '-Command',
            `(Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique) -join ','`,
          ],
          { encoding: 'utf8', shell: false },
        );
        const pids = String(out.stdout || '')
          .split(',')
          .map((s) => s.trim())
          .filter((s) => s && s !== '0');
        for (const pid of pids) {
          spawnSync('taskkill', ['/pid', pid, '/t', '/f'], { stdio: 'ignore' });
        }
      } else {
        spawnSync('bash', ['-lc', `fuser -k ${port}/tcp || true`], {
          stdio: 'ignore',
        });
      }
    } catch (_e) {
      /* ignore */
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  seedDbIfNeeded();
  if (process.env.RMC_E2E_SKIP_MIGRATE !== '1') {
    console.log('=== max-fold: migrate --noinput ===');
    const mig = spawnSync(py, ['manage.py', 'migrate', '--noinput'], {
      cwd: repo,
      env: baseEnv,
      stdio: 'inherit',
      shell: false,
    });
    if (mig.status !== 0) {
      console.error('max-fold: migrate failed');
      process.exit(mig.status || 1);
    }
  }
  console.log('=== max-fold: ensure_superuser ===');
  const su = spawnSync(
    py,
    [
      'manage.py',
      'ensure_superuser',
      '--username',
      process.env.E2E_LOGIN_USER || 'visualqa_admin',
      '--password',
      process.env.E2E_LOGIN_PASSWORD || 'VisualQaPass123!',
      '--no-input',
    ],
    { cwd: repo, env: baseEnv, stdio: 'inherit', shell: false },
  );
  if (su.status !== 0) {
    console.error('max-fold: ensure_superuser failed');
    process.exit(su.status || 1);
  }
  console.log(`=== max-fold: ensure developer sandbox (${tenantSlug}) ===`);
  const sand = spawnSync(
    py,
    [
      'manage.py',
      'ensure_developer_sandbox_tenant',
      `--school-slug=${tenantSlug}`,
      `--password=${process.env.TENANT_SWEEP_PASSWORD || 'Test1234'}`,
    ],
    { cwd: repo, env: baseEnv, stdio: 'inherit', shell: false },
  );
  if (sand.status !== 0) {
    console.error('max-fold: ensure_developer_sandbox_tenant failed');
    process.exit(sand.status || 1);
  }

  fs.mkdirSync(artifactDir, { recursive: true });
  fs.writeFileSync(serverLog, '');
  serverLogFd = fs.openSync(serverLog, 'a');
  console.log(`=== max-fold: runserver 127.0.0.1:${port} ===`);
  server = spawn(
    py,
    ['manage.py', 'runserver', `127.0.0.1:${port}`, '--noreload'],
    {
      cwd: repo,
      env: baseEnv,
      stdio: ['ignore', serverLogFd, serverLogFd],
      shell: false,
    },
  );
  process.on('exit', stopServer);
  for (const sig of ['SIGINT', 'SIGTERM']) {
    process.on(sig, () => {
      stopServer();
      process.exit(130);
    });
  }
  const ready = await waitForServer();
  if (!ready) {
    console.error('max-fold: server not ready; see', serverLog);
    stopServer();
    process.exit(1);
  }
}

async function measureFold(page) {
  return page.evaluate(() => {
    const vh = window.innerHeight || 1;
    const work = document.querySelector('[data-rmc-work-root]');
    const masthead = document.querySelector('[data-rmc-page-masthead]');
    const bands = document.querySelectorAll('[data-rmc-chrome-band]');
    const sparks = document.querySelectorAll('.rmc-page-masthead__spark');
    const roleTabs = document.querySelectorAll('[data-rmc-mission-role-tabs] a[data-rmc-mission-role]');
    const workTop = work ? work.getBoundingClientRect().top : null;
    const mastheadOk = Boolean(masthead);
    const foldsToWork =
      workTop == null ? null : Math.max(0, workTop) / vh;
    return {
      viewportHeight: vh,
      mastheadOk,
      workRootOk: Boolean(work),
      chromeBandCount: bands.length,
      sparklineCount: sparks.length,
      roleTabCount: roleTabs.length,
      workTopPx: workTop,
      foldsToWork,
      foldOk: foldsToWork == null ? false : foldsToWork <= 2.0,
    };
  });
}

async function proveRoute(context, { name, url, login, expectRoleTabs, skipLogin }) {
  const page = await context.newPage();
  const result = {
    name,
    url,
    ok: false,
    failures: [],
    fold: null,
    screenshot: null,
  };
  try {
    if (!skipLogin && login) {
      await login(page);
    }
    const resp = await page.goto(url, {
      waitUntil: 'commit',
      timeout: 120000,
    });
    await page.waitForLoadState('domcontentloaded', { timeout: 120000 }).catch(() => null);
    if (!resp || resp.status() >= 400) {
      result.failures.push(`HTTP ${resp ? resp.status() : 'none'}`);
    }
    await page.waitForTimeout(800);
    const fold = await measureFold(page);
    result.fold = fold;
    if (!fold.mastheadOk) result.failures.push('missing masthead');
    if (!fold.workRootOk) result.failures.push('missing data-rmc-work-root');
    if (!fold.foldOk) {
      result.failures.push(
        `work root too far down (${fold.foldsToWork?.toFixed?.(2) ?? '?'} folds)`,
      );
    }
    if (expectRoleTabs && fold.roleTabCount < 4) {
      result.failures.push(`role tabs ${fold.roleTabCount} < 4`);
    }
    // Money pages should carry at least one sparkline when KPIs exist.
    if (name.includes('money') && fold.sparklineCount < 1) {
      result.failures.push('expected money chip sparkline');
    }
    const shot = path.join(artifactDir, `${name}.png`);
    await page.screenshot({ path: shot, fullPage: false }).catch(() => null);
    result.screenshot = shot;
    result.ok = result.failures.length === 0;

    if (expectRoleTabs && result.ok) {
      const bursar = await page.locator('[data-rmc-mission-role="bursar"]').first();
      if (await bursar.count()) {
        await bursar.click();
        await page.waitForTimeout(600);
        const u = page.url();
        if (!/[?&]mission_role=bursar/.test(u)) {
          result.failures.push('role tab click did not set ?mission_role=bursar');
          result.ok = false;
        } else {
          const fold2 = await measureFold(page);
          if (!fold2.mastheadOk) {
            result.failures.push('masthead lost after role switch');
            result.ok = false;
          }
          const shot2 = path.join(artifactDir, `${name}-bursar.png`);
          await page.screenshot({ path: shot2, fullPage: false });
        }
      }
    }
  } catch (err) {
    result.failures.push(String(err && err.message ? err.message : err));
    result.ok = false;
    const failShot = path.join(artifactDir, `${name}-fail.png`);
    await page.screenshot({ path: failShot, fullPage: false }).catch(() => null);
    result.screenshot = failShot;
  } finally {
    await page.close().catch(() => {});
  }
  return result;
}

async function main() {
  fs.mkdirSync(artifactDir, { recursive: true });
  await startServerIfNeeded();

  const tenantHost = process.env.VISUAL_QA_TENANT_HOST || `${tenantSlug}.runmycampus.com`;
  const tenantBase = `http://${tenantHost}:${port}`;

  console.log(`=== max-fold: tenant base ${tenantBase} ===`);
  console.log(`=== max-fold: manager base ${process.env.MANAGER_BASE_URL} ===`);
  console.log(`=== max-fold: chromium host-resolver ${HOST_RESOLVER_RULES} ===`);

  const browser = await chromium.launch({
    headless: true,
    args: chromiumLaunchArgs(),
  });
  const results = [];

  try {
    const tenCtx = await browser.newContext({
      viewport: { width: 1400, height: 900 },
      ignoreHTTPSErrors: true,
    });
    const tenLoginPage = await tenCtx.newPage();
    await loginTenant(tenLoginPage, {
      username: process.env.TENANT_SWEEP_USERNAME || 'demo.admin',
      password: process.env.TENANT_SWEEP_PASSWORD || 'Test1234',
    });
    await tenLoginPage.close();

    results.push(
      await proveRoute(tenCtx, {
        name: 'tenant-admin-home-mission',
        url: `${tenantBase}/authentication/backend/?mission_role=admin`,
        skipLogin: true,
        expectRoleTabs: true,
      }),
    );
    results.push(
      await proveRoute(tenCtx, {
        name: 'tenant-money-finance',
        url: `${tenantBase}/finance/`,
        skipLogin: true,
        expectRoleTabs: false,
      }),
    );
    await tenCtx.close();

    if (!(await httpOk(`http://127.0.0.1:${port}/observability/health/`, 30000))) {
      console.log('=== max-fold: waiting for server before manager phase ===');
      const ok = await waitForServer(60);
      if (!ok) {
        throw new Error('max-fold: server unhealthy before manager phase');
      }
    }

    const mgrCtx = await browser.newContext({
      viewport: { width: 1400, height: 900 },
      ignoreHTTPSErrors: true,
    });
    const mgrLoginPage = await mgrCtx.newPage();
    try {
      await loginManager(mgrLoginPage);
    } catch (err) {
      console.error('max-fold: manager login failed:', err && err.message ? err.message : err);
      const failShot = path.join(artifactDir, 'manager-login-fail.png');
      await mgrLoginPage.screenshot({ path: failShot, fullPage: false }).catch(() => null);
      throw err;
    }
    await mgrLoginPage.close();

    results.push(
      await proveRoute(mgrCtx, {
        name: 'operator-home-mission',
        url: managerPageUrl('/super/?mission_role=admin'),
        skipLogin: true,
        expectRoleTabs: true,
      }),
    );
    results.push(
      await proveRoute(mgrCtx, {
        name: 'operator-money-billing',
        url: managerPageUrl('/super/billing/'),
        skipLogin: true,
        expectRoleTabs: false,
      }),
    );
    await mgrCtx.close();
  } finally {
    await browser.close().catch(() => {});
    stopServer();
  }

  const failed = results.filter((r) => !r.ok);
  const summary = {
    generated_at: new Date().toISOString(),
    port,
    managerHost,
    artifactDir,
    manager_transport: 'manager.localhost',
    tenant_transport: 'subdomain-map',
    results,
    pass: failed.length === 0,
  };
  fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
  if (failed.length) {
    console.error('MAX_PARITY_FOLD_PROOF_FAIL');
    process.exit(1);
  }
  console.log('MAX_PARITY_FOLD_PROOF_PASS');
}

main().catch((err) => {
  console.error(err);
  stopServer();
  process.exit(1);
});
