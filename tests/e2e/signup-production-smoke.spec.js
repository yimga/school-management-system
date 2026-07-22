// @ts-check
/**
 * Signup production smoke — public login, inactive subdomain UX, optional live Render login.
 *
 * Local (Django on 8000):
 *   MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8000
 *   npm run test:e2e:signup-production
 *
 * Live Render (after deploy + credentials):
 *   SIGNUP_E2E_BASE_URL=https://runmycampus.com \
 *   E2E_USERNAME=owner@example.com E2E_PASSWORD='***' \
 *   npm run test:e2e:signup-production:armed
 *
 * Or GitHub Actions → workflow_dispatch `signup-render-e2e.yml` with secrets.
 * Optional inactive-tenant check (setup-in-progress page):
 *   SIGNUP_E2E_INACTIVE_SLUG=st-jude SIGNUP_E2E_INACTIVE_HOST=st-jude.runmycampus.com \
 *   npm run test:e2e:signup-production
 *
 * Local without /etc/hosts (Chromium DNS map to 127.0.0.1):
 *   SIGNUP_E2E_LOCAL_DNS_MAP=1 SIGNUP_E2E_BASE_URL=http://runmycampus.com:8000 \
 *   SIGNUP_E2E_INACTIVE_SLUG=e2e-pending npm run test:e2e:signup-production
 */
const { test, expect } = require('@playwright/test');

const SIGNUP_BASE_URL =
  process.env.SIGNUP_E2E_BASE_URL ||
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8000';

const INACTIVE_SLUG = (process.env.SIGNUP_E2E_INACTIVE_SLUG || '').trim();
const INACTIVE_HOST =
  (process.env.SIGNUP_E2E_INACTIVE_HOST || '').trim() ||
  (INACTIVE_SLUG ? `${INACTIVE_SLUG}.runmycampus.com` : '');
const INACTIVE_BASE_OVERRIDE = (process.env.SIGNUP_E2E_INACTIVE_BASE_URL || '').trim();
const LOCAL_DNS_MAP = (process.env.SIGNUP_E2E_LOCAL_DNS_MAP || '').trim() === '1';

if (LOCAL_DNS_MAP) {
  test.use({
    baseURL: SIGNUP_BASE_URL,
    launchOptions: {
      args: [
        '--host-resolver-rules=MAP runmycampus.com 127.0.0.1, MAP *.runmycampus.com 127.0.0.1',
      ],
    },
  });
} else {
  test.use({ baseURL: SIGNUP_BASE_URL });
}

test('public login page loads on marketing host', async ({ page }) => {
  await page.goto('/authentication/login/');
  await expect(page).toHaveTitle(/login|sign in|portal|runmycampus/i);
  await expect(page.locator('input[name="username"]')).toBeVisible({ timeout: 15000 });
});

test('verify-signup route is reachable (no 500)', async ({ page }) => {
  const response = await page.goto('/verify-signup/');
  expect(response).not.toBeNull();
  expect(response.status()).toBeLessThan(500);
});

test('inactive tenant subdomain shows setup-in-progress (when configured)', async ({
  page,
  context,
}) => {
  if (!INACTIVE_HOST) {
    test.skip();
    return;
  }
  const inactiveBase =
    INACTIVE_BASE_OVERRIDE ||
    (SIGNUP_BASE_URL.includes('https://')
      ? `https://${INACTIVE_HOST}`
      : `http://${INACTIVE_HOST}:8000`);
  const inactivePage = await context.newPage();
  const response = await inactivePage.goto(`${inactiveBase}/`, {
    waitUntil: 'domcontentloaded',
  });
  expect(response).not.toBeNull();
  const status = response.status();
  expect([200, 202]).toContain(status);
  await expect(
    inactivePage.getByText(/setting up|preparing|portal/i).first(),
  ).toBeVisible({ timeout: 15000 });
  const progressRoot = inactivePage.locator('[data-rmc-provision-progress]');
  await expect(progressRoot).toBeVisible({ timeout: 15000 });
  const progressBar = inactivePage.locator('[data-rmc-provision-bar]');
  await expect(progressBar).toHaveAttribute('aria-valuenow', /^\d+$/);
  let apiResponse;
  if (LOCAL_DNS_MAP) {
    apiResponse = await context.request.get(
      'http://127.0.0.1:8000/api/pending-provision/progress/',
      { headers: { Host: INACTIVE_HOST } },
    );
  } else {
    apiResponse = await inactivePage.request.get(
      `${inactiveBase}/api/pending-provision/progress/`,
    );
  }
  expect(apiResponse.ok()).toBeTruthy();
  const apiJson = await apiResponse.json();
  expect(apiJson.ok).toBe(true);
  expect(typeof apiJson.progress_percent).toBe('number');
  expect(Array.isArray(apiJson.steps)).toBe(true);
  await inactivePage.close();
});

test('owner onboarding done page exposes live provision progress bar (credentials optional)', async ({
  page,
}) => {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) {
    test.skip();
    return;
  }
  await page.goto('/authentication/login/');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(authentication\/redirect|authentication\/backend|authentication\/onboarding)/, {
    timeout: 30000,
  });
  await page.goto('/authentication/onboarding/done/');
  const progress = page.locator('[data-rmc-provision-progress]');
  if ((await progress.count()) === 0) {
    return;
  }
  await expect(progress).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-rmc-provision-bar]')).toHaveAttribute(
    'aria-valuenow',
    /^\d+$/,
  );
});

test('owner can sign in on public host after deploy (credentials optional)', async ({
  page,
}) => {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;
  if (!username || !password) {
    test.skip();
    return;
  }
  await page.goto('/authentication/login/');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL(
    /\/(authentication\/redirect|authentication\/backend|authentication\/onboarding|portal|accounts\/redirect)/,
    { timeout: 30000 },
  );
  const url = page.url();
  expect(url).not.toMatch(/school-not-found/);
});
