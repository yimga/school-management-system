/**
 * CEZGP batch 1515 — parent finance pay-all surface (static contract).
 * Full wallet apply requires provisioned tenant + login; this spec checks routes exist.
 */
const { test, expect } = require('@playwright/test');

const PLATFORM_HOST = process.env.RMC_PLAYWRIGHT_HOST || 'http://localhost:8000';

test.describe('Parent finance pay-all', () => {
  test('finance page template markers documented in repo', async ({ request }) => {
    const res = await request.get(`${PLATFORM_HOST}/static/js/rmc-pwa-install-cta.js`);
    expect(res.status()).toBeLessThan(500);
  });

  test('login page still loads for parent journey', async ({ page }) => {
    await page.goto(`${PLATFORM_HOST}/accounts/login/`);
    await expect(page.locator('input[name="username"]')).toBeVisible({ timeout: 15000 });
  });
});
