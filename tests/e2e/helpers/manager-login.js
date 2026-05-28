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

const LOCAL_DEV_HOSTS = new Set(['127.0.0.1', 'localhost', '::1']);

/**
 * Post-login redirects sometimes land on 127.0.0.1; promote session cookies to the
 * manager host URL once (avoids redirect loops from host-only cookie scope).
 *
 * @param {import('@playwright/test').Page} page
 */
async function ensureManagerHost(page) {
  if (!page.url() || page.url() === 'about:blank') {
    return;
  }
  let current;
  try {
    current = new URL(page.url());
  } catch (_e) {
    return;
  }
  if (current.hostname === MANAGER_HOST) {
    return;
  }
  if (!LOCAL_DEV_HOSTS.has(current.hostname)) {
    return;
  }
  const base = `${MANAGER_BASE_URL.replace(/\/$/, '')}/`;
  const cookies = await page.context().cookies();
  const promoted = cookies
    .filter((cookie) => String(cookie.value || '').trim())
    .map((cookie) => ({
      name: cookie.name,
      value: cookie.value,
      url: base,
      httpOnly: Boolean(cookie.httpOnly),
      secure: false,
      sameSite: cookie.sameSite || 'Lax',
    }));
  if (promoted.length) {
    await page.context().addCookies(promoted);
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

  const loginUrl = `${MANAGER_BASE_URL.replace(/\/$/, '')}/authentication/login/`;
  const currentUrl = page.url() ? new URL(page.url()) : null;
  if (!currentUrl || !/\/authentication\/login\/?$/i.test(currentUrl.pathname)) {
    await page.goto(loginUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
  }
  await page.keyboard.press('Escape').catch(() => {});
  await page.locator('input[name="username"]').waitFor({ state: 'visible', timeout: 60000 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Page.stopLoading').catch(() => {});

  const roleSelect = page.locator('select[name="role"]');
  if (await roleSelect.count()) {
    await roleSelect.selectOption('staff');
  }

  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);

  const leftLogin = page.waitForURL(
    (url) => !/\/authentication\/login\/?$/i.test(url.pathname),
    { timeout: 90000, waitUntil: 'commit' }
  ).catch(() => null);
  const shellReady = page
    .locator(
      '#cp-main-content, [data-rmc-operator-surface-strip], .admin-cp-unified-page, #content'
    )
    .first()
    .waitFor({ state: 'visible', timeout: 90000 })
    .catch(() => null);

  await page.locator('form').first().evaluate((form) => form.requestSubmit());
  await Promise.race([leftLogin, shellReady]);
  await ensureManagerHost(page);

  let pathnameAfterLogin = '';
  try {
    pathnameAfterLogin = new URL(page.url()).pathname;
  } catch (_e) {
    pathnameAfterLogin = '';
  }
  if (/mfa\/verify/i.test(pathnameAfterLogin)) {
    const pythonCmd = process.env.VISUAL_QA_PYTHON || 'python';
    const token = execFileSync(pythonCmd, [TOTP_HELPER], {
      cwd: ROOT_DIR,
      encoding: 'utf8',
      env: {
        ...process.env,
        REDIS_URL: '',
        VISUAL_QA_USERNAME: username,
      },
    }).trim();
    await page.locator('input[name="token"]').fill(token);
    const leftMfa = page
      .waitForURL((url) => !/\/authentication\/mfa\/verify/i.test(url.pathname), {
        timeout: 90000,
        waitUntil: 'commit',
      })
      .catch(() => null);
    const shellAfterMfa = page
      .locator(
        '#cp-main-content, [data-rmc-operator-surface-strip], .admin-cp-unified-page, #content'
      )
      .first()
      .waitFor({ state: 'visible', timeout: 90000 })
      .catch(() => null);
    await page.locator('form').first().evaluate((form) => form.requestSubmit());
    await Promise.race([leftMfa, shellAfterMfa]);
    await ensureManagerHost(page);
  }

  let finalUrl;
  try {
    finalUrl = new URL(page.url());
  } catch (_e) {
    throw new Error(`Manager login failed for ${username}: invalid page URL after submit`);
  }
  if (/\/authentication\/login\/?$/i.test(finalUrl.pathname)) {
    const bodyText = (await page.locator('body').textContent()) || '';
    throw new Error(
      `Manager login failed for ${username} at ${page.url()}. Page text: ${bodyText.slice(0, 240)}`
    );
  }
  if (/mfa\/setup/i.test(finalUrl.pathname)) {
    throw new Error(
      `Manager login blocked by MFA setup for ${username} at ${finalUrl.pathname}. ` +
        'Ensure e2e-playwright TOTP is seeded (run_manager_bulk_confirm_e2e.sh).'
    );
  }
  if (/mfa\/verify/i.test(finalUrl.pathname)) {
    throw new Error(
      `Manager MFA verify did not complete for ${username} at ${finalUrl.pathname}.`
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
  await page.goto(`${MANAGER_BASE_URL.replace(/\/$/, '')}/super/schools/`, {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await ensureManagerHost(page);
  let pathname = '';
  try {
    pathname = new URL(page.url()).pathname;
  } catch (_e) {
    pathname = '';
  }
  if (/\/authentication\/login\/?$/i.test(pathname)) {
    await loginManager(page, opts);
    await page.keyboard.press('Escape').catch(() => {});
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
const { execFileSync } = require('child_process');

const ROOT_DIR = path.join(__dirname, '../../..');
const TOTP_HELPER = path.join(ROOT_DIR, 'scripts/e2e_totp_code.py');

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
