// @ts-check
/** Operator-only offboarding — lifecycle exit status + close-account markers. */
const { test, expect } = require('@playwright/test');
const { TENANT_BASE_URL, loginTenant } = require('./helpers/tenant-login');

test.describe('Tenant offboarding operator-only', () => {
  test('lifecycle command center shows exit status panel', async ({ page }) => {
    await loginTenant(page, { username: process.env.E2E_TENANT_ADMIN_USER || 'demo.admin' });
    await page.goto(`${TENANT_BASE_URL}/school/studio/lifecycle/`, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    await expect(page.locator('[data-rmc-offboarding-exit-status]')).toBeVisible({
      timeout: 30000,
    });
    await expect(page.locator('#section-offboarding')).toBeVisible();
  });

  test('close-account page exposes operator-request controls', async ({ page }) => {
    await loginTenant(page, { username: process.env.E2E_TENANT_ADMIN_USER || 'demo.admin' });
    await page.goto(`${TENANT_BASE_URL}/school/studio/offboarding/`, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    await expect(page.locator('[data-rmc-tenant-offboarding]')).toBeVisible({
      timeout: 30000,
    });
    await expect(page.locator('[data-rmc-tenant-request-closure]')).toBeVisible();
  });

  test('parent data rights page loads for guardian', async ({ page }) => {
    await loginTenant(page, { username: process.env.E2E_TENANT_PARENT_USER || 'demo.parent' });
    await page.goto(`${TENANT_BASE_URL}/portal/parent/data-rights/`, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    await expect(page.locator('h1')).toContainText(/data rights/i, { timeout: 30000 });
  });
});
