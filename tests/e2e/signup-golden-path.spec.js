// @ts-check
/**
 * Golden path: owner login → onboarding done → live provision bar (inactive school).
 *
 * Local:
 *   python manage.py seed_signup_e2e_fixtures
 *   MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8000
 *   SIGNUP_E2E_LOCAL_DNS_MAP=1 E2E_USERNAME=e2e-golden-owner@runmycampus.test \
 *     E2E_PASSWORD='E2eGolden!RmC9' npm run test:e2e:signup-golden-path
 */
const { test, expect } = require('@playwright/test');

const BASE = process.env.SIGNUP_E2E_BASE_URL || 'http://runmycampus.com:8000';
const LOCAL_DNS = process.env.SIGNUP_E2E_LOCAL_DNS_MAP === '1';
const USERNAME = process.env.E2E_USERNAME || 'e2e-golden-owner@runmycampus.test';
const PASSWORD = process.env.E2E_PASSWORD || 'E2eGolden!RmC9';
const TENANT_SLUG = process.env.SIGNUP_E2E_GOLDEN_SLUG || 'e2e-golden';

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

test('owner golden path: login, onboarding done, provision progress bar', async ({
  page,
  context,
}) => {
  const tenantBase = `http://${TENANT_SLUG}.runmycampus.com:8000`;
  const tenantPage = await context.newPage();
  await tenantPage.goto(`${tenantBase}/authentication/login/`);
  await tenantPage.fill('input[name="username"]', USERNAME);
  await tenantPage.fill('input[name="password"]', PASSWORD);
  await tenantPage.click('button[type="submit"]');
  await tenantPage.waitForURL(
    /\/(authentication\/redirect|authentication\/backend|authentication\/onboarding|portal)/,
    { timeout: 45000 },
  );
  await tenantPage.goto(`${tenantBase}/authentication/onboarding/done/`, {
    waitUntil: 'domcontentloaded',
  });
  const progress = tenantPage.locator('[data-rmc-provision-progress]');
  await expect(progress).toBeVisible({ timeout: 20000 });
  await expect(tenantPage.locator('[data-rmc-provision-bar]')).toHaveAttribute(
    'aria-valuenow',
    /^\d+$/,
  );
  await tenantPage.close();
});
