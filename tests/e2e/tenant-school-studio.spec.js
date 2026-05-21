// @ts-check
/**
 * Tenant School Studio — layout markers + abrupt-end guard.
 * Requires Django on TENANT_BASE_URL (default demo-school.runmycampus.com:8012).
 */
const { test, expect } = require('@playwright/test');

const TENANT_HOST = process.env.VISUAL_QA_TENANT_HOST || 'demo-school.runmycampus.com';
const PORT = process.env.VISUAL_QA_PORT || '8012';
const TENANT_BASE = process.env.TENANT_BASE_URL || `http://${TENANT_HOST}:${PORT}`;
const TENANT_SLUG = process.env.TENANT_SWEEP_SLUG || 'demo-school';
const USE_SUBDOMAIN = (process.env.USE_TENANT_SUBDOMAIN || '1').toLowerCase() !== '0';

const STUDIO_ROUTES = [
  '/school/studio/',
  '/school/studio/setup/',
  '/school/studio/readiness/',
  '/school/studio/migration/',
  '/school/studio/help/',
  '/school/studio/launch/',
];

async function loginTenant(page) {
  const loginUrl = USE_SUBDOMAIN
    ? '/authentication/login/'
    : `/t/${TENANT_SLUG}/authentication/login/`;
  await page.goto(`${TENANT_BASE}${loginUrl}`, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.locator('input[name="username"]').fill(process.env.TENANT_E2E_USERNAME || 'admin');
  await page.locator('input[name="password"]').fill(process.env.TENANT_E2E_PASSWORD || 'Sch00l_1234');
  await page.getByRole('button', { name: /log in/i }).click();
  await page.waitForURL((u) => !/\/authentication\/login\/?$/i.test(u.pathname), { timeout: 90000 });
}

async function assertNoAbruptEnd(page) {
  const audit = await page.evaluate(() => {
    const main = document.querySelector('#main-content') || document.querySelector('main');
    const body = document.body;
    const bodyOY = body ? getComputedStyle(body).overflowY : '';
    const stranded = document.querySelectorAll(
      '.rmc-reveal:not([data-rmc-reveal-armed] *)'
    ).length;
    const trapped =
      bodyOY === 'hidden' &&
      body &&
      body.scrollHeight > body.clientHeight + 80 &&
      main &&
      !(main.scrollHeight > main.clientHeight + 2);
    return {
      armed: document.documentElement.getAttribute('data-rmc-reveal-armed'),
      trapped,
      stranded,
    };
  });
  expect(audit.armed).toBeTruthy();
  expect(audit.trapped).toBeFalsy();
}

test.describe('Tenant School Studio', () => {
  test.beforeEach(async ({ page }) => {
    await loginTenant(page);
  });

  for (const route of STUDIO_ROUTES) {
    test(`studio route ${route} renders launch markers`, async ({ page }) => {
      await page.goto(`${TENANT_BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 90000 });
      if (route === '/school/studio/' || route === '/school/studio/readiness/') {
        await expect(page.locator('[data-rmc-tenant-studio-launch-path="1"]')).toBeVisible({
          timeout: 15000,
        });
        await expect(page.locator('[data-rmc-tenant-studio-readiness="1"]')).toBeVisible();
        await expect(page.locator('[data-rmc-tenant-studio-ai-guidance]')).toBeVisible();
      }
      await assertNoAbruptEnd(page);
    });
  }
});
