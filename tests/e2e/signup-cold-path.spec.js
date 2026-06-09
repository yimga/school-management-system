// @ts-check
/**
 * Cold signup golden path — marketing form → verify email → onboarding (no seed).
 *
 * Requires RMC_E2E_SIGNUP_HELPERS=1 on Django and locmem/console email optional.
 *
 * Local:
 *   RMC_E2E_SIGNUP_HELPERS=1 MULTI_TENANT_BASE_DOMAIN=runmycampus.com \
 *     python manage.py runserver 127.0.0.1:8022
 *   SIGNUP_E2E_LOCAL_DNS_MAP=1 SIGNUP_E2E_BASE_URL=http://runmycampus.com:8022 \
 *     npm run test:e2e:signup-cold-path
 */
const { test, expect } = require('@playwright/test');

const BASE = process.env.SIGNUP_E2E_BASE_URL || 'http://runmycampus.com:8022';
const LOCAL_DNS = process.env.SIGNUP_E2E_LOCAL_DNS_MAP === '1';
const HELPERS_ENABLED = process.env.RMC_E2E_SIGNUP_HELPERS === '1';

if (LOCAL_DNS) {
  test.use({
    baseURL: BASE,
    launchOptions: {
      args: [
        '--host-resolver-rules=MAP runmycampus.com 127.0.0.1, MAP *.runmycampus.com 127.0.0.1',
      ],
    },
  });
} else {
  test.use({ baseURL: BASE });
}

test('cold signup: form → verify token → onboarding entry', async ({ page, context }) => {
  if (!HELPERS_ENABLED) {
    test.skip();
    return;
  }

  const stamp = Date.now();
  const slug = `e2e-cold-${stamp}`;
  const email = `e2e-cold-${stamp}@runmycampus.test`;
  const schoolName = `E2E Cold School ${stamp}`;

  await page.goto('/signup/');
  await page.fill('input[name="name"]', schoolName);
  await page.fill('input[name="slug"]', slug);
  await page.fill('input[name="email"]', email);
  const country = page.locator('select[name="country_code"]');
  if ((await country.count()) > 0) {
    await country.selectOption({ index: 1 });
  }
  await page.click('button[type="submit"]');
  await expect(page.getByText(/check your email/i).first()).toBeVisible({
    timeout: 30000,
  });

  const baseUrl = new URL(BASE);
  const helperOrigin = LOCAL_DNS
    ? `http://127.0.0.1:${baseUrl.port || '8000'}`
    : BASE.replace(/\/$/, '');
  const tokenUrl = `${helperOrigin}/api/e2e/signup-verification-token/?email=${encodeURIComponent(email)}&slug=${encodeURIComponent(slug)}`;

  let token = '';
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const tokenResp = await context.request.get(tokenUrl);
    if (tokenResp.ok()) {
      const body = await tokenResp.json();
      if (body.ok && body.token) {
        token = body.token;
        break;
      }
    }
    await page.waitForTimeout(500);
  }
  expect(token, 'verification token from E2E helper').toBeTruthy();

  await page.goto(`/verify-signup/?token=${token}`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL(/onboarding|authentication\/redirect|signup/, {
    timeout: 60000,
  });
  const url = page.url();
  expect(url).toMatch(/onboarding|authentication/);
});
