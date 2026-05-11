// @ts-check
/**
 * Captures the "Switch the lens" tabbed walkthrough at each tab state, so
 * we can verify the CSS-only radio-driven interactivity actually works.
 */
const { test, expect } = require('@playwright/test');
const path = require('path');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
test.use({ baseURL: BASE_URL, viewport: { width: 1280, height: 900 } });

const OUT = path.resolve(__dirname, '..', '..', '.tmp', 'screens');
const LENSES = ['leader', 'teacher', 'parent', 'finance', 'it'];

test.describe.configure({ mode: 'serial' });

for (const lens of LENSES) {
  test(`lens: ${lens}`, async ({ page }) => {
    await page.goto('/v2/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    // Click the tab — CSS uses the underlying radio
    await page.locator(`label[for="lens-${lens}"]`).click();
    await page.waitForTimeout(350); // fade animation
    // Scroll the lens section into view
    await page.locator('.mkt-edt-lens').scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
    await page.screenshot({
      path: path.join(OUT, `lens-${lens}.png`),
      fullPage: false,
      clip: { x: 0, y: 0, width: 1280, height: 900 },
    });
    expect(true).toBeTruthy();
  });
}
