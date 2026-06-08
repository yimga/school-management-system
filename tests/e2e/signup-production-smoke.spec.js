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
 *   npm run test:e2e:signup-production
 *
 * Optional inactive-tenant check (setup-in-progress page):
 *   SIGNUP_E2E_INACTIVE_SLUG=st-jude SIGNUP_E2E_INACTIVE_HOST=st-jude.runmycampus.com \
 *   npm run test:e2e:signup-production
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

test.use({ baseURL: SIGNUP_BASE_URL });

test('public login page loads on marketing host', async ({ page }) => {
  await page.goto('/authentication/login/');
  await expect(page).toHaveTitle(/login|sign in|portal|runmycampus/i);
  await expect(
    page
      .getByRole('heading', { name: /log in|sign in/i })
      .or(page.locator('input[name="username"]')),
  ).toBeVisible({ timeout: 15000 });
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
  const inactiveBase = SIGNUP_BASE_URL.includes('https://')
    ? `https://${INACTIVE_HOST}`
    : `http://${INACTIVE_HOST}:8000`;
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
  await inactivePage.close();
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
