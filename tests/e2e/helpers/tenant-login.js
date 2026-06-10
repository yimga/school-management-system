// @ts-check
/**
 * Tenant login for Playwright.
 *
 * Default: path-tenant on 127.0.0.1 (avoids Chrome HSTS/SSL upgrade on *.runmycampus.com).
 * Set TENANT_E2E_SUBDOMAIN=1 to use demo-school.runmycampus.com host mapping instead.
 */

const TENANT_SLUG = process.env.TENANT_SLUG || 'demo-school';
const TENANT_PORT = process.env.VISUAL_QA_PORT || '8012';
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
    timeout: 60000,
  });
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
  if (!(await userField.isVisible().catch(() => false))) {
    return;
  }
  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('admin').catch(() => roleSelect.selectOption('staff'));
  }
  await userField.fill(username);
  await page.locator('input[name="password"]').first().fill(password);
  const leftLogin = page
    .waitForURL((url) => !/\/authentication\/login\/?$/i.test(url.pathname), {
      timeout: 90000,
      waitUntil: 'commit',
    })
    .catch(() => null);
  await page.locator('form').first().evaluate((form) => form.requestSubmit());
  await leftLogin;
  await ensurePathTenantHost(page);
  await page.waitForLoadState('domcontentloaded');
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function openAdminUserMenu(page) {
  const userCard = page.locator('.admin-sidebar-user-card-inner').first();
  await userCard.waitFor({ state: 'visible', timeout: 15000 });
  await userCard.click();
  await page.waitForFunction(() => {
    const card = document.querySelector('.admin-sidebar-user-card-inner');
    return card?.getAttribute('aria-expanded') === 'true';
  });
}

module.exports = {
  loginTenant,
  openAdminUserMenu,
  ensurePathTenantHost,
  TENANT_BASE_URL,
  TENANT_SLUG,
};
