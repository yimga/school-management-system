// @ts-check
/**
 * Gear-up i18n: pricing matrix renders without horizontal overflow on mobile.
 */
const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8000';

test.use({
  baseURL: MARKETING_BASE_URL,
  viewport: { width: 390, height: 844 },
});

test('pricing matrix fits mobile viewport', async ({ page }) => {
  const res = await page.goto('/pricing/', { waitUntil: 'domcontentloaded', timeout: 45000 });
  expect(res).toBeTruthy();
  expect(res.status()).toBeLessThan(400);

  const matrix = page.locator('.mkt-v3-pricing-matrix, [data-mkt-pricing-matrix]');
  if (await matrix.count()) {
    await matrix.first().scrollIntoViewIfNeeded();
  }

  const overflowX = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - doc.clientWidth;
  });
  expect(overflowX).toBeLessThanOrEqual(2);
});
