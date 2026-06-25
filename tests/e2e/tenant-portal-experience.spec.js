// @ts-check
/**
 * Portal experience presets + per-role themes + command-strip score band + workflow density.
 * Runs on tenant-phase-chromium (auto webServer via playwright.config.js).
 */
const { test, expect } = require('@playwright/test');
const { TENANT_BASE_URL, loginTenant } = require('./helpers/tenant-login');

async function openPortalExperiencePresets(page) {
  await page.goto(`${TENANT_BASE_URL}/siteconfig/feature-control/`, {
    waitUntil: 'domcontentloaded',
    timeout: 120000,
  });
  if (page.url().includes('/authentication/login')) {
    await page.goto(`${TENANT_BASE_URL}/siteconfig/school-configuration/cockpit/configure/`, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
  }
  const portalTab = page.locator(
    '[data-cat="portal_experience"], #feature-cat-tab-portal_experience'
  );
  if (await portalTab.count()) {
    await portalTab.first().click();
  }
  if (!(await page.locator('[data-rmc-portal-experience-presets="1"]').count())) {
    await page.goto(`${TENANT_BASE_URL}/siteconfig/school-configuration/cockpit/configure/`, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
  }
}

test.describe('Tenant portal experience', () => {
  test('tenant admin sees school-wide and per-role preset markers', async ({ page }) => {
    await loginTenant(page, { username: process.env.E2E_TENANT_ADMIN_USER || 'demo.admin' });
    await openPortalExperiencePresets(page);
    await expect(page.locator('[data-rmc-portal-experience-presets="1"]')).toBeVisible({
      timeout: 30000,
    });
    await expect(page.locator('[data-rmc-portal-role-experience-presets="1"]')).toBeVisible();
  });

  test('parent dashboard command strip exposes score band metadata', async ({ page }) => {
    await loginTenant(page, { username: process.env.E2E_TENANT_PARENT_USER || 'parent' });
    await page.goto(`${TENANT_BASE_URL}/portal/parent/`, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    const strip = page.locator('[data-rmc-tenant-experience-command="1"]');
    await expect(strip).toBeVisible({ timeout: 30000 });
    await expect(strip).toHaveAttribute('data-rmc-score-band', /ready|progress|attention/);
  });

  test('parent workflow exposes workflow contract + section nav', async ({ page }) => {
    await loginTenant(page, { username: process.env.E2E_TENANT_PARENT_USER || 'parent' });
    await page.goto(`${TENANT_BASE_URL}/portal/parent/workflow/`, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    const portal = page.locator('[data-rmc-tenant-workflow-portal="1"]');
    await expect(portal).toBeVisible({ timeout: 30000 });
    await expect(portal).toHaveAttribute('data-rmc-readiness-state', /visible|blocked/);
    await expect(portal).toHaveAttribute('data-rmc-mobile-proof', 'responsive');
    await expect(page.locator('.tp-workflow-section-nav')).toBeVisible();
  });

  test('parent workflow mobile hides desktop step grid', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginTenant(page, { username: process.env.E2E_TENANT_PARENT_USER || 'parent' });
    await page.goto(`${TENANT_BASE_URL}/portal/parent/workflow/`, {
      waitUntil: 'domcontentloaded',
      timeout: 120000,
    });
    await expect(page.locator('[data-rmc-mobile-workflow="1"]')).toBeVisible({
      timeout: 30000,
    });
    await expect(page.locator('#tp-workflow-steps')).toBeHidden();
  });
});
