// @ts-check
/**
 * Shared manager-host login for Playwright (visual QA user).
 */

const MANAGER_HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const MANAGER_PORT = process.env.VISUAL_QA_PORT || '8012';
const MANAGER_BASE_URL =
  process.env.MANAGER_BASE_URL ||
  process.env.BASE_URL ||
  `http://${MANAGER_HOST}:${MANAGER_PORT}`;

/**
 * Post-login redirects sometimes land on 127.0.0.1; re-open on manager host so
 * HostUrlconfMiddleware serves config.manager_urls + unified admin chrome.
 *
 * @param {import('@playwright/test').Page} page
 */
async function ensureManagerHost(page) {
  const current = new URL(page.url());
  if (current.hostname === MANAGER_HOST) {
    return;
  }
  const target = new URL(current.pathname + current.search + current.hash, MANAGER_BASE_URL);
  await page.goto(target.toString(), {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ username?: string; password?: string }} [opts]
 */
async function loginManager(page, opts = {}) {
  const username = opts.username || process.env.VISUAL_QA_USERNAME || 'visualqa_admin';
  const password = opts.password || process.env.VISUAL_QA_PASSWORD || 'VisualQaPass123!';

  await page.goto('/authentication/login/', {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });

  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }

  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /log in/i }).click();

  const leftLogin = page.waitForURL(
    (url) => !/\/authentication\/login\/?$/i.test(url.pathname),
    { timeout: 90000, waitUntil: 'domcontentloaded' }
  );
  const shellReady = page
    .locator(
      '#cp-main-content, [data-rmc-operator-surface-strip], .admin-cp-unified-page, #content'
    )
    .first()
    .waitFor({ state: 'visible', timeout: 90000 });

  await Promise.race([leftLogin, shellReady]);
  await ensureManagerHost(page);

  if (/\/authentication\/login\/?$/i.test(new URL(page.url()).pathname)) {
    const bodyText = (await page.locator('body').textContent()) || '';
    throw new Error(
      `Manager login failed for ${username}. Page text: ${bodyText.slice(0, 240)}`
    );
  }

  const host = new URL(page.url()).hostname;
  if (host !== MANAGER_HOST) {
    throw new Error(
      `Expected manager host ${MANAGER_HOST} after login; got ${host} (${page.url()})`
    );
  }
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function hasManagerSession(page) {
  const cookies = await page.context().cookies();
  return cookies.some(
    (cookie) =>
      cookie.name === 'rmc_manager_sessionid' ||
      cookie.name === 'sessionid' ||
      cookie.name.endsWith('sessionid')
  );
}

/**
 * @param {import('@playwright/test').Page} page
 */
/**
 * Ensure an authenticated manager control-plane session (re-login if needed).
 *
 * @param {import('@playwright/test').Page} page
 * @param {{ username?: string; password?: string }} [opts]
 */
async function ensureManagerSession(page, opts = {}) {
  await ensureManagerHost(page);
  await page.goto('/super/', {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  const onLogin =
    (await page.locator('input[name="username"]').count()) > 0 ||
    /\/authentication\/login\/?$/i.test(new URL(page.url()).pathname);
  if (onLogin) {
    await loginManager(page, opts);
    await page.goto('/super/', {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
  }
}

async function needsManagerLogin(page) {
  const raw = page.url() || '';
  if (!raw || raw === 'about:blank') {
    return !(await hasManagerSession(page));
  }
  const url = new URL(raw);
  if (url.hostname !== MANAGER_HOST) {
    return true;
  }
  if (/\/authentication\/login\/?$/i.test(url.pathname)) {
    return true;
  }
  return false;
}

const path = require('path');

const AUTH_STATE_PATH = path.join(
  __dirname,
  '../../../artifacts/manager-playwright-auth.json'
);

module.exports = {
  loginManager,
  ensureManagerHost,
  ensureManagerSession,
  hasManagerSession,
  needsManagerLogin,
  MANAGER_BASE_URL,
  MANAGER_HOST,
  AUTH_STATE_PATH,
};