// @ts-check
/**
 * Tenant login for Playwright.
 *
 * Default: path-tenant on 127.0.0.1 (avoids Chrome HSTS/SSL upgrade on *.runmycampus.com).
 * Set TENANT_E2E_SUBDOMAIN=1 to use demo-school.runmycampus.com host mapping instead.
 */

const { execFileSync } = require('child_process');
const path = require('path');

const ROOT_DIR = path.join(__dirname, '..', '..', '..');
const TOTP_HELPER = path.join(ROOT_DIR, 'scripts', 'e2e_totp_code.py');
const DEFAULT_TOTP_HEX = 'eab95095c004f245721ba0fa7ebf82d5dc73';

const TENANT_SLUG = process.env.TENANT_SLUG || 'demo-school';
const TENANT_PORT = (
  process.env.VISUAL_QA_TENANT_PHASE_PORT ||
  process.env.VISUAL_QA_PORT ||
  '8013'
).trim();
const TENANT_HOST = process.env.VISUAL_QA_TENANT_HOST || `${TENANT_SLUG}.runmycampus.com`;
const TENANT_USE_SUBDOMAIN = process.env.TENANT_E2E_SUBDOMAIN === '1';
const TENANT_PATH_BASE = `http://127.0.0.1:${TENANT_PORT}/t/${TENANT_SLUG}`;
const TENANT_SUBDOMAIN_BASE = `http://${TENANT_HOST}:${TENANT_PORT}`;

const TENANT_BASE_URL = (
  process.env.TENANT_E2E_BASE_URL ||
  process.env.PLAYWRIGHT_TENANT_BASE_URL ||
  process.env.VISUAL_QA_TENANT_URL ||
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

/**
 * @param {string} username
 */
function fetchTenantTotpToken(username) {
  const pythonCmd = process.env.VISUAL_QA_PYTHON || 'python';
  return execFileSync(pythonCmd, [TOTP_HELPER], {
    cwd: ROOT_DIR,
    env: {
      ...process.env,
      E2E_LOGIN_USER: username,
      VISUAL_QA_TOTP_HEX_KEY:
        process.env.VISUAL_QA_TOTP_HEX_KEY ||
        process.env.VISUAL_QA_TOTP_HEX ||
        DEFAULT_TOTP_HEX,
    },
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
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
  const tokenInput = page.locator('input[name="token"]');
  await tokenInput.waitFor({ state: 'visible', timeout: 60000 });
  const submitMfa = async () => {
    await tokenInput.fill(fetchTenantTotpToken(username));
    const leftMfa = page
      .waitForURL((url) => !/\/authentication\/mfa\/verify/i.test(url.pathname), {
        timeout: 90000,
        waitUntil: 'commit',
      })
      .catch(() => null);
    await page
      .locator('form[method="post"] button[type="submit"]')
      .first()
      .click({ timeout: 30000 });
    await leftMfa;
    await ensurePathTenantHost(page);
  };
  await submitMfa();
  try {
    pathname = new URL(page.url()).pathname;
  } catch (_e) {
    pathname = '';
  }
  if (/\/authentication\/mfa\/verify/i.test(pathname)) {
    await page.waitForTimeout(1500);
    await submitMfa();
  }
  if (/\/authentication\/mfa\/setup/i.test(new URL(page.url()).pathname)) {
    throw new Error(
      `Tenant MFA setup required for ${username}. Seed e2e-playwright TOTP in run_tenant_phase_e2e.mjs.`,
    );
  }
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ username?: string; password?: string }} [opts]
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

  await page.goto(loginUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const userField = page.locator('input[name="username"], input[name="email"]').first();
  await userField.waitFor({ state: 'visible', timeout: 30000 });

  const loginForm = page
    .locator('form')
    .filter({ has: page.locator('input[name="username"]') })
    .first();
  const roleSelect = loginForm.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }
  await userField.fill(username);
  await loginForm.locator('input[name="password"]').first().fill(password);
  // Timing trap only blocks sub-second bot submits; brief pause is enough.
  await page.waitForTimeout(1200);
  const leftLogin = page
    .waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), {
      timeout: 90000,
      waitUntil: 'commit',
    })
    .catch(() => null);
  // requestSubmit avoids overlay / pointer-event traps on the login CTA.
  await loginForm.evaluate((form) => {
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });
  await leftLogin;
  await ensurePathTenantHost(page);
  await completeTenantMfaIfPresent(page, username);
  await page.waitForLoadState('domcontentloaded');
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
  fetchTenantTotpToken,
  TENANT_BASE_URL,
  TENANT_SLUG,
};
