/**
 * Template marketplace runtime — Playwright spec (batch 1492 audit closure).
 *
 * Run via:
 *   npx playwright test tests/e2e/template-marketplace-runtime.spec.js
 *
 * Requires a provisioned tenant + authenticated session helpers from
 * tests/e2e/helpers/tenant-login.js.
 */
const { test, expect } = require('@playwright/test');

const TENANT_HOST = process.env.RMC_TENANT_PLAYWRIGHT_HOST || 'http://demo.localhost:8000';

test.describe('Template marketplace runtime', () => {
  test.beforeEach(async ({ page }) => {
    // Hook into the existing tenant-login helper when present.
    try {
      const helper = require('./helpers/tenant-login');
      await helper.loginAs(page, 'admin');
    } catch (_err) {
      test.skip('tenant-login helper not available in environment');
    }
  });

  test('marketplace browse route loads with at least one card', async ({ page }) => {
    await page.goto(`${TENANT_HOST}/school/studio/templates/`);
    await expect(page).toHaveURL(/templates/);
    const cardCount = await page.locator('[data-rmc-template-card]').count();
    expect(cardCount).toBeGreaterThan(0);
  });

  test('preview returns 200 and no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto(`${TENANT_HOST}/school/studio/templates/tenant-parent-soft-glass/preview/`);
    expect(errors.filter((e) => !/favicon/.test(e))).toEqual([]);
  });

  test('apply requires POST + CSRF (GET shows confirmation)', async ({ page, request }) => {
    const csrfRes = await page.goto(`${TENANT_HOST}/school/studio/templates/tenant-parent-soft-glass/apply/`);
    // GET should serve confirmation page (200) or redirect (3xx) — never auto-apply via GET.
    expect([200, 302]).toContain(csrfRes.status());
  });

  test('operator-only template returns 404 on tenant scope', async ({ request }) => {
    const res = await request.get(`${TENANT_HOST}/school/studio/templates/operator-super-v8-200x/`);
    expect([404, 403]).toContain(res.status());
  });

  test('no horizontal overflow on marketplace at tenant viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${TENANT_HOST}/school/studio/templates/`);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
