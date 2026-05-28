// @ts-check
//
// Glocal batch 1537 — teacher role-home at 390px under RTL (ar).
// Lane 2: requires Django + provisioned tenant (see helpers/tenant-login.js).

const { test, expect } = require('@playwright/test');
const { tenantLogin, tenantUrl, TENANT_ORIGIN } = require('./helpers/tenant-login');

const SKIP = process.env.SKIP_TEACHER_RTL_E2E === '1';
const describeRtl = SKIP ? test.describe.skip : test.describe;

async function horizontalOverflowPx(page) {
  return page.evaluate(() =>
    Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
  );
}

describeRtl('teacher dashboard — RTL mobile 390px', () => {
  test.use({
    viewport: { width: 390, height: 844 },
    serviceWorkers: 'block',
  });

  test('no horizontal bleed with dir=rtl and canvas scroll policy', async ({ page }) => {
    test.setTimeout(180000);
    const loggedIn = await tenantLogin(page, { role: 'teacher' });
    test.skip(!loggedIn, 'tenant login unavailable');

    const dashboardUrl = tenantUrl('/portal/teacher/?language=ar');

    await page.context().addCookies([
      {
        name: 'django_language',
        value: 'ar',
        url: tenantUrl('/'),
      },
    ]);

    const cookies = await page.context().cookies();
    const csrf = cookies.find((c) => c.name === 'csrftoken')?.value || '';
    const setLangUrl = tenantUrl('/i18n/setlang/persist/');
    await page.request.post(setLangUrl, {
      form: { language: 'ar', next: dashboardUrl },
      headers: csrf
        ? { 'X-CSRFToken': csrf, Referer: dashboardUrl }
        : { Referer: dashboardUrl },
      maxRedirects: 0,
    });

    await page.goto(dashboardUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 90000,
    });

    await expect(
      page.locator('body.dashboard-page-teacher').first(),
    ).toBeVisible({ timeout: 90000 });

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
  });
});
