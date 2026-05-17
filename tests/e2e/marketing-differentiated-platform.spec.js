// @ts-check
/**
 * Marketing tranche-2 differentiated platform pages (verb-canonical + security).
 * Run with marketing host mapping, e.g.:
 *   MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8010
 *   MARKETING_BASE_URL=http://runmycampus.com:8010 npx playwright test tests/e2e/marketing-differentiated-platform.spec.js
 */
const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8000';

test.use({ baseURL: MARKETING_BASE_URL });

const CASES = [
  { path: '/pay/fees/', marker: 'data-mkt-platform-fees-payments' },
  { path: '/communicate/inbox/', marker: 'data-mkt-platform-parent-portal' },
  { path: '/teach/workspace/', marker: 'data-mkt-platform-teacher-portal' },
  { path: '/run/analytics/', marker: 'data-mkt-platform-analytics' },
  { path: '/platform/security/', marker: 'data-mkt-platform-security' },
];

for (const { path, marker } of CASES) {
  test(`${path} renders ${marker}`, async ({ page }) => {
    const res = await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 45000 });
    expect(res?.status() ?? 0, `${path} HTTP`).toBeLessThan(400);
    await expect(page.locator(`[${marker}]`)).toBeVisible({ timeout: 15000 });
    await expect(page.locator('nav.mkt-navbar')).toBeVisible();
  });
}
