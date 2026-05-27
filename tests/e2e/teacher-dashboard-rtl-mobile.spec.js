// @ts-check
//
// Glocal batch 1537 — teacher role-home at 390px under RTL (ar).
// Lane 2: requires Django + provisioned tenant (see helpers/tenant-login.js).

const { test, expect } = require('@playwright/test');
const { tenantLogin, tenantUrl } = require('./helpers/tenant-login');

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
    test.setTimeout(120000);
    const loggedIn = await tenantLogin(page, { role: 'staff' });
    test.skip(!loggedIn, 'tenant login unavailable');

    await page.goto(tenantUrl('/portal/teacher/?language=ar'), {
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
