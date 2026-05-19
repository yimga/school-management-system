/**
 * Gear-up a11y: axe on homepage impact sections (bell, persona via day|role, globe).
 */
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const BASE =
  process.env.MARKETING_BASE_URL ||
  process.env.MARKETING_E2E_BASE ||
  'http://runmycampus.com:8000';

test.describe('marketing gear2 a11y', () => {
  test('homepage impact regions pass axe', async ({ page }) => {
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-mkt-day-role]', { timeout: 15000 });

    const results = await new AxeBuilder({ page })
      .include('[data-mkt-day-role]')
      .include('.mkt-edt-globe__map--interactive')
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test('bell steps respond to keyboard', async ({ page }) => {
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    const bell = page.locator('[data-mkt-bell-clock] [data-bell-step]').first();
    await bell.waitFor({ timeout: 15000 });
    await bell.focus();
    await page.keyboard.press('ArrowRight');
    await expect(page.locator('[data-mkt-bell-clock] [data-bell-step].is-active')).toHaveCount(1);
  });
});
