// @ts-check
/**
 * Tenant login for Playwright.
 *
 * Default: path-tenant on 127.0.0.1 (avoids Chrome HSTS/SSL upgrade on *.runmycampus.com).
 * Set TENANT_E2E_SUBDOMAIN=1 to use demo-school.runmycampus.com host mapping instead.
 */

const crypto = require('crypto');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.join(__dirname, '..', '..', '..');
const TOTP_HELPER = path.join(ROOT_DIR, 'scripts', 'e2e_totp_code.py');
const DEFAULT_TOTP_HEX = 'eab95095c004f245721ba0fa7ebf82d5dc73';

const TENANT_SLUG = process.env.TENANT_SLUG || 'demo-school';

function resolveTenantPort() {
  const explicitBase =
    process.env.TENANT_E2E_BASE_URL ||
    process.env.PLAYWRIGHT_TENANT_BASE_URL ||
    process.env.VISUAL_QA_TENANT_URL ||
    process.env.TENANT_BASE_URL ||
    '';
  if (explicitBase) {
    try {
      const parsed = new URL(explicitBase);
      if (parsed.port) {
        return parsed.port;
      }
    } catch (_e) {
      /* ignore malformed base URL */
    }
  }
  return (
    process.env.VISUAL_QA_TENANT_PHASE_PORT ||
    process.env.VISUAL_QA_PORT ||
    '8013'
  ).trim();
}

const TENANT_PORT = resolveTenantPort();
const TENANT_HOST = process.env.VISUAL_QA_TENANT_HOST || `${TENANT_SLUG}.runmycampus.com`;
const TENANT_PATH_BASE = `http://127.0.0.1:${TENANT_PORT}/t/${TENANT_SLUG}`;
const TENANT_SUBDOMAIN_BASE = `http://${TENANT_HOST}:${TENANT_PORT}`;

const EXPLICIT_TENANT_BASE = (
  process.env.TENANT_E2E_BASE_URL ||
  process.env.PLAYWRIGHT_TENANT_BASE_URL ||
  process.env.VISUAL_QA_TENANT_URL ||
  process.env.TENANT_BASE_URL ||
  ''
).replace(/\/$/, '');

const TENANT_USE_SUBDOMAIN =
  process.env.TENANT_E2E_SUBDOMAIN === '1' ||
  (EXPLICIT_TENANT_BASE
    ? !/^https?:\/\/127\.0\.0\.1(?::|$)/i.test(EXPLICIT_TENANT_BASE)
    : false);

const TENANT_BASE_URL = (
  EXPLICIT_TENANT_BASE ||
  (TENANT_USE_SUBDOMAIN ? TENANT_SUBDOMAIN_BASE : TENANT_PATH_BASE)
).replace(/\/$/, '');

/**
 * Keep path-tenant sessions on 127.0.0.1 after Django canonical subdomain redirects.
 * @param {import('@playwright/test').Page} page
 */
async function ensurePathTenantHost(page) {
  if (TENANT_USE_SUBDOMAIN || !TENANT_BASE_URL.includes('127.0.0.1')) {
    return;
  }
  let current;
  try {
    current = new URL(page.url());
  } catch (_e) {
    return;
  }
  if (current.hostname === '127.0.0.1') {
    return;
  }
  // tenant-phase-chromium maps *.runmycampus.com → 127.0.0.1; canonical subdomain URLs are valid.
  if (current.hostname.endsWith('.runmycampus.com')) {
    return;
  }
  const cookieUrl = `http://127.0.0.1:${TENANT_PORT}/`;
  const cookies = await page.context().cookies();
  const promoted = cookies
    .filter((cookie) => String(cookie.value || '').trim())
    .map((cookie) => ({
      name: cookie.name,
      value: cookie.value,
      url: cookieUrl,
      httpOnly: Boolean(cookie.httpOnly),
      secure: false,
      sameSite: cookie.sameSite || 'Lax',
    }));
  if (promoted.length) {
    await page.context().addCookies(promoted);
  }
  const suffix = `${current.pathname}${current.search}${current.hash}`;
  const pathSuffix = suffix.startsWith(`/t/${TENANT_SLUG}`)
    ? suffix.slice(`/t/${TENANT_SLUG}`.length) || '/'
    : suffix;
  await page.goto(`${TENANT_PATH_BASE}${pathSuffix}`, {
    waitUntil: 'domcontentloaded',
    timeout: 120000,
  });
}

function resolvePython() {
  if (process.env.VISUAL_QA_PYTHON) {
    return process.env.VISUAL_QA_PYTHON;
  }
  const candidates = [
    path.join(ROOT_DIR, '.venv', 'Scripts', 'python.exe'),
    path.join(ROOT_DIR, '.venv', 'bin', 'python'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function resolveTenantTotpHexKey() {
  return (
    process.env.VISUAL_QA_TOTP_HEX_KEY ||
    process.env.VISUAL_QA_TOTP_HEX ||
    DEFAULT_TOTP_HEX
  ).trim();
}

/**
 * Resolve SQLite DB_FILE for Django TOTP export (same DB as runserver).
 * @returns {string | undefined}
 */
function resolveE2eDbFile() {
  const explicit = (process.env.DB_FILE || '').trim();
  if (explicit) {
    return explicit;
  }
  const envLocal = path.join(ROOT_DIR, '.env.local');
  if (fs.existsSync(envLocal)) {
    const match = fs.readFileSync(envLocal, 'utf8').match(/^DB_FILE=(.+)$/m);
    if (match && match[1].trim()) {
      return match[1].trim();
    }
  }
  for (const name of ['db_playwright_p0_closure.sqlite3', 'db_working.sqlite3', 'db.sqlite3']) {
    const candidate = path.join(ROOT_DIR, name);
    try {
      if (fs.statSync(candidate).size > 4096) {
        return candidate;
      }
    } catch (_e) {
      /* missing */
    }
  }
  return undefined;
}

/**
 * @param {string} username
 * @returns {NodeJS.ProcessEnv}
 */
function djangoE2eSubprocessEnv(username) {
  const env = {
    ...process.env,
    REDIS_URL: '',
    RMC_FORCE_DB_SESSIONS: '1',
    E2E_LOGIN_USER: username,
    VISUAL_QA_USERNAME: username,
  };
  const dbFile = resolveE2eDbFile();
  if (dbFile) {
    env.DB_FILE = dbFile;
  }
  return env;
}

/**
 * @param {string} hexKey
 * @param {number} [step]
 * @param {number} [digits]
 */
function totpFromHexKey(hexKey, step = 30, digits = 6) {
  const counter = Math.floor(Date.now() / 1000 / step);
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const hmac = crypto.createHmac('sha1', Buffer.from(hexKey, 'hex')).update(buf).digest();
  const off = hmac[hmac.length - 1] & 0xf;
  const bin =
    ((hmac[off] & 0x7f) << 24) |
    ((hmac[off + 1] & 0xff) << 16) |
    ((hmac[off + 2] & 0xff) << 8) |
    (hmac[off + 3] & 0xff);
  return String(bin % 10 ** digits).padStart(digits, '0');
}

/**
 * @param {string} username
 */
function fetchTenantTotpToken(username) {
  if (process.env.RMC_E2E_BYPASS_MFA === '1') {
    return '123456';
  }
  const pythonCmd = resolvePython();
  try {
    return execFileSync(pythonCmd, [TOTP_HELPER], {
      cwd: ROOT_DIR,
      env: djangoE2eSubprocessEnv(username),
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  } catch (_e) {
    const hexKey = resolveTenantTotpHexKey();
    if (hexKey) {
      return totpFromHexKey(hexKey);
    }
    throw _e;
  }
}

async function waitForNextTotpWindow(step = 30) {
  const msIntoStep = (Date.now() / 1000 % step) * 1000;
  const waitMs = step * 1000 - msIntoStep + 750;
  await new Promise((resolve) => setTimeout(resolve, waitMs));
}

/**
 * Login PoW must finish before submit or the server rejects the POST.
 * @param {import('@playwright/test').Page} page
 */
async function waitForRevealArmed(page) {
  await page
    .waitForFunction(
      () => document.documentElement.getAttribute('data-rmc-reveal-armed') !== null,
      { timeout: 60000 },
    )
    .catch(() => {});
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function waitForLoginPowComplete(page) {
  const pow = page.locator('#rmc-pow');
  if (!(await pow.count())) {
    return;
  }
  await page
    .waitForFunction(
      () => {
        const field = document.querySelector('input[name="pow_nonce"]');
        return Boolean(field && String(field.value || '').trim().length > 0);
      },
      { timeout: 90000 },
    )
    .catch(async () => {
      await page
        .locator('#rmc-pow-status')
        .filter({ hasText: /verified/i })
        .first()
        .waitFor({ state: 'visible', timeout: 30000 });
    });
}

/**
 * @param {string} username
 * @param {string | undefined} roleOverride
 */
function resolveTenantLoginRole(username, roleOverride) {
  if (roleOverride) {
    return roleOverride;
  }
  const normalized = String(username || '').toLowerCase();
  if (normalized.includes('parent')) {
    return 'parent';
  }
  if (normalized.includes('student')) {
    return 'student';
  }
  return 'staff';
}

async function completeTenantSecurityPostureIfPresent(page) {
  let pathname = '';
  try {
    pathname = new URL(page.url()).pathname;
  } catch (_e) {
    return;
  }
  if (!/\/authentication\/profile\/security\/review\/?$/i.test(pathname)) {
    return;
  }
  const reviewForm = page.locator('form[method="post"]').first();
  if (!(await reviewForm.count())) {
    return;
  }
  const leftReview = page
    .waitForURL((url) => !/\/authentication\/profile\/security\/review\/?$/i.test(url.pathname), {
      timeout: 90000,
      waitUntil: 'commit',
    })
    .catch(() => null);
  await reviewForm.evaluate((form) => {
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });
  await leftReview;
  await ensurePathTenantHost(page);
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} username
 */
async function completeTenantMfaIfPresent(page, username) {
  let pathname = '';
  try {
    pathname = new URL(page.url()).pathname;
  } catch (_e) {
    return;
  }
  if (!/\/authentication\/mfa\/verify/i.test(pathname)) {
    return;
  }
  await waitForRevealArmed(page);
  await page
    .evaluate(() => {
      document.documentElement.setAttribute('data-rmc-reveal-armed', '1');
    })
    .catch(() => {});
  const tokenInput = page.locator('input[name="token"]');
  await tokenInput.waitFor({ state: 'visible', timeout: 60000 });
  const mfaForm = page.locator('form[method="post"]').filter({ has: tokenInput }).first();

  const submitMfa = async () => {
    const dirtyDiscard = page.locator('.rmc-fi-savebar.is-dirty button').filter({ hasText: /discard/i });
    if (await dirtyDiscard.count()) {
      await dirtyDiscard.first().click({ timeout: 3000 }).catch(() => {});
    }
    const bypassMfa = process.env.RMC_E2E_BYPASS_MFA === '1';
    const token = bypassMfa ? '123456' : fetchTenantTotpToken(username);
    await tokenInput.fill(token);
    const remember = page.locator('input[name="remember_device"]');
    if (await remember.count()) {
      await remember.check({ timeout: 3000 }).catch(() => {});
    }
    const leftMfa = page
      .waitForURL((url) => !/\/authentication\/mfa\/verify/i.test(url.pathname), {
        timeout: 30000,
        waitUntil: 'commit',
      })
      .catch(() => null);
    const shellAfterMfa = page
      .locator(
        '#main-content, .portal-main-col, .rmc-app-shell, .backend-v2-main, [data-rmc-tenant-header-100x]',
      )
      .first()
      .waitFor({ state: 'visible', timeout: 30000 })
      .catch(() => null);
    if (await mfaForm.count()) {
      await mfaForm.evaluate((form) => {
        if (typeof form.requestSubmit === 'function') {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
    } else {
      await page
        .locator('form[method="post"] button[type="submit"]')
        .first()
        .click({ timeout: 30000 });
    }
    await Promise.race([leftMfa, shellAfterMfa, page.waitForLoadState('domcontentloaded')]);
    await ensurePathTenantHost(page);
  };

  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (attempt > 0 && process.env.RMC_E2E_BYPASS_MFA !== '1') {
      await waitForNextTotpWindow();
    }
    await submitMfa();
    try {
      pathname = new URL(page.url()).pathname;
    } catch (_e) {
      pathname = '';
    }
    if (!/\/authentication\/mfa\/verify/i.test(pathname)) {
      break;
    }
    await page.waitForTimeout(800);
  }
  let finalPath = '';
  try {
    finalPath = new URL(page.url()).pathname;
  } catch (_e) {
    finalPath = '';
  }
  if (/\/authentication\/mfa\/setup/i.test(finalPath)) {
    throw new Error(
      `Tenant MFA setup required for ${username}. Seed e2e-playwright TOTP in run_tenant_phase_e2e.mjs.`,
    );
  }
  if (/\/authentication\/mfa\/verify/i.test(finalPath)) {
    const bodyText = (await page.locator('body').textContent()) || '';
    throw new Error(
      `Tenant MFA verify did not complete for ${username} at ${page.url()}. ` +
        `Page text: ${bodyText.slice(0, 240)}`,
    );
  }
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ username?: string; password?: string; role?: string }} [opts]
 */
async function loginTenant(page, opts = {}) {
  const username =
    opts.username ||
    process.env.E2E_TENANT_USER ||
    process.env.VISUAL_QA_USERNAME ||
    'demo.admin';
  const password =
    opts.password ||
    process.env.E2E_TENANT_PASSWORD ||
    process.env.VISUAL_QA_PASSWORD ||
    process.env.ADMIN_PASSWORD ||
    'Test1234';
  const loginUrl = `${TENANT_BASE_URL}/authentication/login/`;
  const loginRole = resolveTenantLoginRole(username, opts.role);

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto(loginUrl, { waitUntil: 'domcontentloaded', timeout: 120000 });
    let currentPath = '';
    try {
      currentPath = new URL(page.url()).pathname;
    } catch (_e) {
      currentPath = '';
    }
    if (/\/authentication\/mfa\/verify/i.test(currentPath)) {
      await completeTenantMfaIfPresent(page, username);
      break;
    }
    await waitForRevealArmed(page);
    const userField = page
      .locator('#login-username, input[name="username"], input[name="email"]')
      .first();
    await userField.waitFor({ state: 'visible', timeout: 120000 });

    const loginForm = page
      .locator('form')
      .filter({ has: page.locator('input[name="username"]') })
      .first();
    const roleSelect = loginForm.locator('select[name="role"]');
    if (await roleSelect.count()) {
      await roleSelect.selectOption(loginRole);
    }
    await userField.fill(username);
    await loginForm.locator('input[name="password"]').first().fill(password);
    await waitForLoginPowComplete(page);

    const leftLogin = page
      .waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), {
        timeout: 90000,
        waitUntil: 'commit',
      })
      .catch(() => null);
    await loginForm.evaluate((form) => {
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.submit();
      }
    });
    await leftLogin;

    let loginPath = '';
    try {
      loginPath = new URL(page.url()).pathname;
    } catch (_e) {
      loginPath = '';
    }
    if (!/\/authentication\/login\/?$/i.test(loginPath)) {
      break;
    }
    if (attempt < 2) {
      await page.waitForTimeout(2000);
    }
  }

  let loginPath = '';
  try {
    loginPath = new URL(page.url()).pathname;
  } catch (_e) {
    loginPath = '';
  }
  if (/\/authentication\/login\/?$/i.test(loginPath)) {
    const alertText =
      (await page.locator('.alert, [role="alert"]').first().textContent().catch(() => '')) || '';
    const bodyText = (await page.locator('body').textContent()) || '';
    throw new Error(
      `Tenant login failed for ${username} (still on login page). ` +
        `Alert: ${alertText.trim().slice(0, 120)} Body: ${bodyText.slice(0, 200)}`,
    );
  }
  await ensurePathTenantHost(page);
  await completeTenantMfaIfPresent(page, username);
  await completeTenantSecurityPostureIfPresent(page);
  await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => {});
}

/**
 * Open the tenant staff user menu (backend header dropdown or unfold sidebar card).
 * Tenant hosts redirect /admin/ → /authentication/backend/, so backend is the default surface.
 * @param {import('@playwright/test').Page} page
 */
async function openTenantUserMenu(page) {
  const userCard = page.locator('.admin-sidebar-user-card-inner').first();
  if (await userCard.isVisible().catch(() => false)) {
    await userCard.click();
    await page.waitForFunction(() => {
      const card = document.querySelector('.admin-sidebar-user-card-inner');
      return card?.getAttribute('aria-expanded') === 'true';
    });
    return;
  }
  const trigger = page.locator('#userDropdownBtn').first();
  await trigger.waitFor({ state: 'visible', timeout: 15000 });
  await trigger.click();
}

/** @deprecated Use openTenantUserMenu — tenant /admin/ redirects to backend. */
async function openAdminUserMenu(page) {
  return openTenantUserMenu(page);
}

module.exports = {
  loginTenant,
  openTenantUserMenu,
  openAdminUserMenu,
  ensurePathTenantHost,
  completeTenantMfaIfPresent,
  completeTenantSecurityPostureIfPresent,
  fetchTenantTotpToken,
  resolveE2eDbFile,
  djangoE2eSubprocessEnv,
  TENANT_BASE_URL,
  TENANT_SLUG,
};
