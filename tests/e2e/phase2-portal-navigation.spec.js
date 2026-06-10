// @ts-check
/**
 * Phase 2 — tenant portal user-dropdown logout visibility at all viewports.
 *
 * Requires Django on VISUAL_QA_PORT with demo-school host mapped:
 *   npm run test:e2e:phase2-portal
 */
const { test, expect } = require('@playwright/test');
const { loginTenant, TENANT_BASE_URL } = require('./helpers/tenant-login');

const VIEWPORTS = [
  { label: '320px', width: 320, height: 640 },
  { label: '768px', width: 768, height: 900 },
  { label: '1440px', width: 1440, height: 900 },
];

test.describe('Phase 2 portal navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginTenant(page);
    const backendUrl = `${TENANT_BASE_URL.replace(/\/$/, '')}/authentication/backend/`;
    const response = await page.goto(backendUrl, { waitUntil: 'domcontentloaded' });
    expect(response?.status()).toBeLessThan(400);
  });

  for (const vp of VIEWPORTS) {
    test(`portal logout visible at ${vp.label}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      const trigger = page.locator('#userDropdownBtn').first();
      await expect(trigger).toBeVisible({ timeout: 15000 });
      await trigger.click();

      const logout = page.locator('[data-rmc-nav-logout]').first();
      await expect(logout).toBeVisible({ timeout: 8000 });

      const box = await logout.boundingBox();
      expect(box).toBeTruthy();
      if (!box) return;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(vp.width + 2);
      expect(box.y + box.height).toBeLessThanOrEqual(vp.height + 2);
    });
  }

  test('tenant html declares fluid layout', async ({ page }) => {
    const layout = await page.locator('html').getAttribute('data-rmc-layout');
    expect(layout).toBe('fluid');
  });
});
