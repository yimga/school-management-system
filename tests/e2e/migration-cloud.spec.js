// @ts-check
// Migration Cloud connector wizard — tenant setup surface.
const { test, expect } = require('@playwright/test');

const TENANT_BASE_URL = process.env.TENANT_BASE_URL || 'http://localhost:8000';
const TENANT_PATH_PREFIX = process.env.TENANT_PATH_PREFIX || '/t/demo-school';
const CONNECTOR_HOME = `${TENANT_BASE_URL}${TENANT_PATH_PREFIX}/school/setup/migration-cloud/`;

test.describe('Migration Cloud connector wizard', () => {
  test('home page markers when server available', async ({ page }) => {
    test.skip(!process.env.MIGRATION_CLOUD_E2E, 'Set MIGRATION_CLOUD_E2E=1 with Django running');

    const errors = [];
    page.on('pageerror', (err) => errors.push(String(err)));

    const response = await page.goto(CONNECTOR_HOME, { waitUntil: 'domcontentloaded' });
    expect(response && response.status() < 500).toBeTruthy();
    await expect(page.locator('[data-rmc-migration-cloud-surface]')).toBeVisible();
    await expect(page.locator('[data-rmc-page-fold-nav]')).toHaveCount(1);
    expect(errors, `console errors: ${errors.join('; ')}`).toEqual([]);
  });

  test('connect form exposes authorization checkboxes', async ({ page }) => {
    test.skip(!process.env.MIGRATION_CLOUD_E2E, 'Set MIGRATION_CLOUD_E2E=1 with Django running');

    await page.goto(`${CONNECTOR_HOME}connect/`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#authorization_confirmed')).toBeVisible();
    await expect(page.locator('#terms_acknowledged')).toBeVisible();
    await expect(page.locator('#source_url')).toBeVisible();
  });
});
