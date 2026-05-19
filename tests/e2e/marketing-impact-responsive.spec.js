// @ts-check
/**
 * Sweep 2 — impact sections stack without horizontal scroll (iPhone SE scale).
 * Requires Django on runmycampus.com host.
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

async function assertNoHorizontalOverflow(page) {
  const overflowX = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - doc.clientWidth;
  });
  expect(overflowX, 'document horizontal overflow (overflowX guard)').toBeLessThanOrEqual(2);
}

test.describe('marketing impact responsive', () => {
  test('homepage impact sections stack cleanly on mobile', async ({ page }) => {
    const res = await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    expect(res).toBeTruthy();
    expect(res.status()).toBeLessThan(400);

    await expect(page.locator('[data-mkt-live-pulse]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-mkt-day-role]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-mkt-bell-clock]')).toBeVisible({ timeout: 15000 });

    await page.locator('[data-mkt-day-role]').scrollIntoViewIfNeeded();
    await assertNoHorizontalOverflow(page);

    const roleTab = page.locator('[data-day-role-tab="role"]');
    if (await roleTab.count()) {
      await roleTab.click();
      await expect(page.locator('[data-mkt-persona-tabs]')).toBeVisible({ timeout: 10000 });
      const personaBtn = page.locator('[data-persona-tab="teacher"]');
      if (await personaBtn.count()) {
        await personaBtn.click();
      }
      await assertNoHorizontalOverflow(page);
    }

    const globe = page.locator('.mkt-edt-globe');
    if (await globe.count()) {
      await globe.scrollIntoViewIfNeeded();
      await expect(page.locator('.mkt-world-map')).toBeVisible({ timeout: 10000 });
      const pin = page.locator('.mkt-globe-pin__btn').first();
      if (await pin.count()) {
        await pin.focus();
        await page.keyboard.press('Enter');
      }
      await assertNoHorizontalOverflow(page);
    }
  });

  test('lane short routes resolve', async ({ page }) => {
    const laneChecks = [
      { path: '/academics/', sel: '.mkt-lane-academics' },
      { path: '/admissions/', sel: '[data-mkt-admissions-steps]' },
      { path: '/finance/', sel: '.mkt-lane-finance' },
    ];
    for (const { path, sel } of laneChecks) {
      const res = await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 45000 });
      expect(res, path).toBeTruthy();
      expect(res.status(), path).toBeLessThan(400);
      await expect(page.locator(sel)).toBeVisible({ timeout: 15000 });
      await assertNoHorizontalOverflow(page);
    }
  });
});
