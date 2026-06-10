// @ts-check
/**
 * Phase 2 — tenant portal user-dropdown logout visibility at all viewports.
 *
 * Requires Django on VISUAL_QA_PORT with demo tenant path, e.g.:
 *   /t/demo-school/authentication/backend/
 */
const { test, expect } = require('@playwright/test');

const TENANT_BASE =
  process.env.TENANT_E2E_BASE_URL ||
  process.env.VISUAL_QA_TENANT_URL ||
  'http://127.0.0.1:8012/t/demo-school';

const VIEWPORTS = [
  { label: '320px', width: 320, height: 640 },
  { label: '768px', width: 768, height: 900 },
  { label: '1440px', width: 1440, height: 900 },
];

test.describe('Phase 2 portal navigation', () => {
  test.beforeEach(async ({ page }) => {
    const loginUrl = `${TENANT_BASE.replace(/\/$/, '')}/authentication/login/`;
    await page.goto(loginUrl, { waitUntil: 'domcontentloaded' });
    const userField = page.locator('input[name="username"], input[name="email"]').first();
    const passField = page.locator('input[name="password"]').first();
    if (await userField.isVisible().catch(() => false)) {
      await userField.fill(process.env.E2E_TENANT_USER || 'admin');
      await passField.fill(process.env.E2E_TENANT_PASSWORD || 'Sch00l_1234');
      await page.locator('button[type="submit"], input[type="submit"]').first().click();
      await page.waitForLoadState('domcontentloaded');
    }
    const backendUrl = `${TENANT_BASE.replace(/\/$/, '')}/authentication/backend/`;
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
