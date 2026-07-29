// @ts-check
/**
 * Dashboard pack Apply → backend grid smoke.
 * Verifies the per-user pack switcher persists a choice and reshapes backend modules.
 *
 * Run (tenant phase project, Django on VISUAL_QA_PORT):
 *   npx playwright test tests/e2e/dashboard-pack-backend-grid.spec.js --project=tenant-phase-chromium
 */
const { test, expect } = require('@playwright/test');
const { loginTenant, TENANT_BASE_URL } = require('./helpers/tenant-login');

const BACKEND_URL = `${TENANT_BASE_URL}/authentication/backend/`;
const FINANCE_PACK = 'finance-office-ledger';
const EXECUTIVE_PACK = 'school-admin-executive';

/** @param {import('@playwright/test').Page} page */
async function dismissBlockingChrome(page) {
  await page.keyboard.press('Escape').catch(() => {});
  const dismiss = page.locator(
    '[data-bs-dismiss="modal"], [data-rmc-onboarding-dismiss], button:has-text("Skip"), button:has-text("Not now"), button:has-text("Close")',
  );
  if (await dismiss.count()) {
    await dismiss.first().click({ timeout: 5000 }).catch(() => {});
  }
}

test.describe('Dashboard pack switcher on backend grid', () => {
  test.beforeEach(async ({ page }) => {
    await loginTenant(page, { username: process.env.E2E_TENANT_USER || 'demo.admin' });
  });

  test('Apply finance pack hides Top-Performing module', async ({ page }) => {
    await page.goto(BACKEND_URL, { waitUntil: 'domcontentloaded', timeout: 120000 });
    await dismissBlockingChrome(page);

    const switcher = page.locator('[data-rmc-dashboard-pack-switcher]');
    if (!(await switcher.count())) {
      test.skip(true, 'Dashboard pack switcher not rendered for this user/school.');
      return;
    }

    await switcher.locator('summary').click({ timeout: 15000 });

    const financeRadio = page.locator(
      `input[name="dashboard_pack"][value="${FINANCE_PACK}"]`,
    );
    if (!(await financeRadio.count())) {
      test.skip(true, `Pack ${FINANCE_PACK} not offered for this role.`);
      return;
    }

    const topPerforming = page.locator('[data-widget-id="backend-top-performing"]');
    const hadTopPerforming = await topPerforming.isVisible().catch(() => false);

    await financeRadio.check({ force: true });

    const reloadPromise = page.waitForLoadState('load', { timeout: 120000 });
    await page.locator('[data-rmc-dashboard-pack-apply]').click();
    await reloadPromise;
    await dismissBlockingChrome(page);

    await expect(page.locator('body')).toHaveAttribute(
      'data-rmc-active-dashboard-pack',
      FINANCE_PACK,
      { timeout: 30000 },
    );
    await expect(topPerforming).toBeHidden({ timeout: 15000 });

    if (hadTopPerforming) {
      await expect(topPerforming).toHaveCount(0);
    }
  });

  test('Apply executive pack can show Top-Performing module', async ({ page }) => {
    await page.goto(BACKEND_URL, { waitUntil: 'domcontentloaded', timeout: 120000 });
    await dismissBlockingChrome(page);

    const switcher = page.locator('[data-rmc-dashboard-pack-switcher]');
    if (!(await switcher.count())) {
      test.skip(true, 'Dashboard pack switcher not rendered for this user/school.');
      return;
    }

    await switcher.locator('summary').click({ timeout: 15000 });

    const executiveRadio = page.locator(
      `input[name="dashboard_pack"][value="${EXECUTIVE_PACK}"]`,
    );
    if (!(await executiveRadio.count())) {
      test.skip(true, `Pack ${EXECUTIVE_PACK} not offered for this role.`);
      return;
    }

    await executiveRadio.check({ force: true });

    const reloadPromise = page.waitForLoadState('load', { timeout: 120000 });
    await page.locator('[data-rmc-dashboard-pack-apply]').click();
    await reloadPromise;
    await dismissBlockingChrome(page);

    await expect(page.locator('body')).toHaveAttribute(
      'data-rmc-active-dashboard-pack',
      EXECUTIVE_PACK,
      { timeout: 30000 },
    );

    const topPerforming = page.locator('[data-widget-id="backend-top-performing"]');
    if (await topPerforming.count()) {
      await expect(topPerforming).toBeVisible({ timeout: 15000 });
    }
  });
});
