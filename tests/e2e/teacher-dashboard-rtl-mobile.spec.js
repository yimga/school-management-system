// @ts-check
//
// Glocal batch 1537 — teacher role-home at 390px under RTL (ar).
// Lane 2: requires Django + provisioned tenant (see helpers/tenant-login.js).
//
// Run:
//   TENANT_BASE_URL=http://gilead-school.runmycampus.com:8000 \
//     npx playwright test tests/e2e/teacher-dashboard-rtl-mobile.spec.js
//
// Skip when no server:
//   SKIP_TEACHER_RTL_E2E=1 npx playwright test ...

const { test, expect } = require('@playwright/test');
const { tenantLogin, tenantUrl, tenantPrefix } = require('./helpers/tenant-login');

const SKIP = process.env.SKIP_TEACHER_RTL_E2E === '1';
const describeRtl = SKIP ? test.describe.skip : test.describe;

async function horizontalOverflowPx(page) {
  return page.evaluate(() =>
    Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  );
}

describeRtl('teacher dashboard — RTL mobile 390px', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('no horizontal bleed with dir=rtl and canvas scroll policy', async ({ page }) => {
    const loggedIn = await tenantLogin(page, { role: 'teacher' });
    test.skip(!loggedIn, 'tenant login unavailable');

    const dashboardPath = '/teacher/';
    const dashboardUrl = tenantUrl(dashboardPath);
    const origin = new URL(dashboardUrl).origin;
    await page.context().addCookies([
      {
        name: 'django_language',
        value: 'ar',
        url: origin,
        path: '/',
      },
    ]);
    await page.goto(dashboardUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });

    const dir = await page.evaluate(
      () => document.documentElement.getAttribute('dir') || '',
    );
    expect(dir, '<html dir> under ar locale').toBe('rtl');

    const scrollPolicy = await page.evaluate(
      () => document.body.getAttribute('data-rmc-cp-scroll') || '',
    );
    expect(scrollPolicy, 'teacher dashboard canvas scroll').toBe('canvas');

    const overflow = await horizontalOverflowPx(page);
    expect(overflow, 'horizontal overflow px').toBeLessThanOrEqual(2);

    await expect(
      page.locator('body.dashboard-page-teacher').first(),
    ).toBeVisible({ timeout: 15000 });
  });
});
