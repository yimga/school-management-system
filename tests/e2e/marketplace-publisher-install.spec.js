// @ts-check
const { test, expect } = require('@playwright/test');
const { ensureManagerSession, MANAGER_BASE_URL } = require('./helpers/manager-login');
const { tenantLogin, tenantUrl } = require('./helpers/tenant-login');

const APP_SLUG = process.env.MKT_E2E_APP_SLUG || 'e2e-install-widget';
const TENANT_ADMIN =
  process.env.MKT_E2E_TENANT_USER || 'e2e-mkt-admin@runmycampus.test';
const TENANT_PASSWORD =
  process.env.MKT_E2E_TENANT_PASSWORD || 'E2eMktInstall!RmC9';

test.describe('Marketplace publisher install', () => {
  test('manager approves pending review then tenant installs app', async ({ page }) => {
    test.setTimeout(180000);

    await ensureManagerSession(page);
    const governanceUrl = `${MANAGER_BASE_URL.replace(/\/$/, '')}/super/marketplace/`;
    await page.goto(governanceUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });

    const approveForm = page
      .locator('form[data-rmc-mkt-review-approve]')
      .filter({ hasText: 'E2E Install Widget' })
      .first();
    await expect(approveForm).toBeVisible({ timeout: 60000 });
    await approveForm.locator('button[type="submit"]').click();

    await page.waitForURL(/\/super\/marketplace\/governance\/?/i, {
      timeout: 60000,
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('body')).toContainText(/approved/i);

    await tenantLogin(page, {
      username: TENANT_ADMIN,
      password: TENANT_PASSWORD,
      role: 'admin',
    });

    const catalogUrl = tenantUrl('/settings/app-catalog/');
    await page.goto(catalogUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    await expect(page.locator('body')).toContainText('E2E Install Widget', {
      timeout: 60000,
    });

    const appRow = page.locator('body *').filter({ hasText: 'E2E Install Widget' }).first();
    await expect(appRow).toBeVisible({ timeout: 60000 });
    const installBtn = page.locator('[data-rmc-open-install-impact][data-app-id]').first();
    await installBtn.click({ timeout: 30000 });

    const modal = page.locator('#rmcInstallImpactModal');
    await expect(modal).toBeVisible({ timeout: 60000 });

    const scopeChecks = modal.locator('input[name="consented_scopes"]');
    const scopeCount = await scopeChecks.count();
    for (let i = 0; i < scopeCount; i += 1) {
      await scopeChecks.nth(i).check();
    }

    const confirmBtn = modal.locator('#rmcInstallImpactConfirmBtn');
    await expect(confirmBtn).toBeEnabled({ timeout: 60000 });
    await confirmBtn.click();

    await page.waitForURL(/\/marketplace\/(apps|installed)/i, {
      timeout: 90000,
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('body')).toContainText(/install/i);
  });
});
