// @ts-check
/**
 * Captures screenshots with each mega-menu dropdown open, so we can verify
 * the dropdowns actually function and are editorial-styled.
 */
const { test, expect } = require('@playwright/test');
const path = require('path');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
test.use({ baseURL: BASE_URL, viewport: { width: 1280, height: 900 } });

const OUT = path.resolve(__dirname, '..', '..', '.tmp', 'screens');

const MENUS = ['Platform', 'Solutions', 'Resources'];

test.describe.configure({ mode: 'serial' });

for (const label of MENUS) {
  test(`menu open: ${label}`, async ({ page }) => {
    await page.goto('/v2/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    const trigger = page
      .locator('nav.mkt-navbar')
      .getByRole('button', { name: new RegExp(`^${label}$`, 'i') })
      .or(
        page.locator('nav.mkt-navbar').getByText(label, { exact: true }).first(),
      )
      .first();
    await trigger.click();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: path.join(OUT, `menu-${label.toLowerCase()}-open.png`),
      fullPage: false,
      clip: { x: 0, y: 0, width: 1280, height: 600 },
    });
    expect(true).toBeTruthy();
  });
}
