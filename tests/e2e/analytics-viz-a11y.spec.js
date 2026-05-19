// @ts-check
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SKIP_AXE = process.env.SKIP_AXE === '1';

test.use({ baseURL: BASE_URL });

const ROUTES = [
  { path: '/marketing/', mount: false },
  { path: '/t/demo-school/portal/analytics/', mount: true, auth: true },
];

async function assertAxe(page, label) {
  if (SKIP_AXE) return;
  const { violations } = await new AxeBuilder({ page })
    .include('[data-rmc-tenant-overview], .rmc-viz-root')
    .analyze();
  const blocking = violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious',
  );
  expect.soft(blocking, `axe on ${label}`).toEqual([]);
}

test.describe('unified analytics viz a11y', () => {
  for (const route of ROUTES) {
    test(`mount contract ${route.path}`, async ({ page }) => {
      if (route.auth) {
        test.skip(!process.env.ANALYTICS_VIZ_AUTH, 'Set ANALYTICS_VIZ_AUTH=1 with logged-in storage');
      }
      const resp = await page.goto(route.path, { waitUntil: 'domcontentloaded' });
      expect(resp?.status()).toBeLessThan(500);
      if (route.mount) {
        const mount = page.locator('[data-rmc-tenant-overview]');
        await expect.soft(mount).toHaveCount(1, { timeout: 15000 });
        await expect.soft(mount).toHaveAttribute('data-tenant-id', /.+/);
      }
      await assertAxe(page, route.path);
    });
  }

  test('loader script is referenced when flag on', async ({ page }) => {
    await page.goto('/marketing/', { waitUntil: 'domcontentloaded' });
    const loader = page.locator('script[src*="rmc-analytics-viz-loader"]');
    await expect.soft(loader).toHaveCount(1);
  });
});
