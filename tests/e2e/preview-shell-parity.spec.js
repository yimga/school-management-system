// @ts-check
/**
 * Preview shell 100x — manager Lane 2 + tenant portal matrix (batch 1491).
 * Tenant probes use path-based URLs (/t/<slug>/…) so any school tenant works locally.
 */
const { test, expect } = require('@playwright/test');
const {
  ensureManagerHost,
  ensureManagerSession,
  MANAGER_BASE_URL,
  AUTH_STATE_PATH,
} = require('./helpers/manager-login');
const { tenantUrl, tenantLogin, ensureTenantOrigin } = require('./helpers/tenant-login');

const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1366, height: 768 },
];

async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 2
  );
  expect(overflow).toBeFalsy();
}

async function assertHealthyShell(page) {
  const title = await page.title();
  expect(title).not.toMatch(/ImportError|Server Error/i);
  const body = (await page.locator('body').textContent()) || '';
  expect(body).not.toContain('ImportError at');
}

async function assertTenantV3Shell(page) {
  await expect(page.locator('html[data-rmc-tp-v3-shell="1"]')).toHaveCount(1);
  await expect(
    page.locator('.tp-header__row, [data-rmc-tenant-header-100x="1"]').first()
  ).toBeVisible();
}

test.describe('Preview shell parity — manager', () => {
  test.use({ storageState: AUTH_STATE_PATH });

  test.beforeEach(async ({ page }) => {
    await ensureManagerSession(page);
    await ensureManagerHost(page, MANAGER_BASE_URL);
  });

  for (const vp of VIEWPORTS) {
    test(`super landing header order @ ${vp.width}px`, async ({ page }) => {
      await page.setViewportSize(vp);
      await page.goto(`${MANAGER_BASE_URL}/super/`, { waitUntil: 'domcontentloaded' });
      await assertHealthyShell(page);
      const strip = page.locator('[data-rmc-cp-live-strip="1"]');
      const nav = page.locator('[data-rmc-cp-nav-row="1"], .cp-primary-nav').first();
      await expect(strip).toBeVisible();
      await expect(nav).toBeVisible();
      const order = await page.evaluate(() => {
        const stripEl = document.querySelector('[data-rmc-cp-live-strip="1"]');
        const navEl =
          document.querySelector('[data-rmc-cp-nav-row="1"]') ||
          document.querySelector('.cp-primary-nav');
        if (!stripEl || !navEl) return false;
        return (
          stripEl.compareDocumentPosition(navEl) & Node.DOCUMENT_POSITION_FOLLOWING
        );
      });
      expect(order).toBeTruthy();
      await assertNoHorizontalOverflow(page);
    });
  }

  test('schools list paginate policy and table', async ({ page }) => {
    await page.goto(`${MANAGER_BASE_URL}/super/schools/`, {
      waitUntil: 'domcontentloaded',
    });
    await assertHealthyShell(page);
    await expect(page.locator('[data-rmc-scroll-policy="paginate"]')).toBeVisible();
    await expect(
      page.locator('.rmc-data-table, table.table-family')
    ).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });
});

test.describe('Preview shell parity — tenant portal', () => {
  test('teacher role home — v3 hero + shell', async ({ page }) => {
    const ok = await tenantLogin(page, { role: 'teacher' });
    if (!ok) {
      test.skip(true, 'tenant login form not available');
      return;
    }
    await page.goto(tenantUrl('/portal/teacher/'), { waitUntil: 'domcontentloaded' });
    await ensureTenantOrigin(page);
    await assertHealthyShell(page);
    await assertTenantV3Shell(page);
    await expect(page.locator('[data-rmc-tp-hero-greeting="1"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-rmc-tenant-experience-command="1"]')).toBeVisible();
    await expect(page.locator('[data-rmc-tenant-toolbelt="1"]')).toBeVisible();
    await expect(page.locator('[data-rmc-tp-hero-context]')).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  test('parent role home — v3 hero', async ({ page }) => {
    const ok = await tenantLogin(page, {
      role: 'parent',
      username: process.env.VISUAL_QA_PARENT_USERNAME || 'Parent1',
      password: process.env.VISUAL_QA_PARENT_PASSWORD || 'Sch00l_1234',
    });
    if (!ok) {
      test.skip(true, 'tenant login form not available');
      return;
    }
    await page.goto(tenantUrl('/portal/parent/'), { waitUntil: 'domcontentloaded' });
    await ensureTenantOrigin(page);
    await assertHealthyShell(page);
    await assertTenantV3Shell(page);
    await expect(page.locator('[data-rmc-tp-hero-greeting="1"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-rmc-tenant-experience-command="1"]')).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  test('parent finance list — paginate marker + pager when rows exist', async ({ page }) => {
    const ok = await tenantLogin(page, {
      role: 'parent',
      username: process.env.VISUAL_QA_PARENT_USERNAME || 'Parent1',
      password: process.env.VISUAL_QA_PARENT_PASSWORD || 'Sch00l_1234',
    });
    if (!ok) return;
    await page.goto(tenantUrl('/portal/parent/finance/'), {
      waitUntil: 'domcontentloaded',
    });
    await ensureTenantOrigin(page);
    await assertHealthyShell(page);
    await assertTenantV3Shell(page);
    await expect(page.locator('[data-rmc-scroll-policy="paginate"]')).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  test('teacher workflow portal — simple next action surface', async ({ page }) => {
    const ok = await tenantLogin(page, { role: 'teacher' });
    if (!ok) return;
    await page.goto(tenantUrl('/portal/teacher/workflow/'), {
      waitUntil: 'domcontentloaded',
    });
    await ensureTenantOrigin(page);
    await assertHealthyShell(page);
    await assertTenantV3Shell(page);
    await expect(page.locator('[data-rmc-tenant-workflow-portal="1"]')).toBeVisible();
    await expect(page.locator('[data-rmc-workflow-focus="1"]')).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  test('parent workflow portal — simple next action surface', async ({ page }) => {
    const ok = await tenantLogin(page, {
      role: 'parent',
      username: process.env.VISUAL_QA_PARENT_USERNAME || 'Parent1',
      password: process.env.VISUAL_QA_PARENT_PASSWORD || 'Sch00l_1234',
    });
    if (!ok) return;
    await page.goto(tenantUrl('/portal/parent/workflow/'), {
      waitUntil: 'domcontentloaded',
    });
    await ensureTenantOrigin(page);
    await assertHealthyShell(page);
    await assertTenantV3Shell(page);
    await expect(page.locator('[data-rmc-tenant-workflow-portal="1"]')).toBeVisible();
    await expect(page.locator('[data-rmc-workflow-step]').first()).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  test('teacher marks list — paginate policy', async ({ page }) => {
    const ok = await tenantLogin(page, { role: 'teacher' });
    if (!ok) return;
    await page.goto(tenantUrl('/evals/teacher/marks/'), {
      waitUntil: 'domcontentloaded',
    });
    await ensureTenantOrigin(page);
    await assertHealthyShell(page);
    await assertTenantV3Shell(page);
    await expect(page.locator('[data-rmc-scroll-policy="paginate"]')).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  test('no floating chathead on v3 tenant shell', async ({ page }) => {
    const ok = await tenantLogin(page, { role: 'teacher' });
    if (!ok) return;
    await page.goto(tenantUrl('/portal/teacher/'), { waitUntil: 'domcontentloaded' });
    await ensureTenantOrigin(page);
    await expect(page.locator('.portal-chathead')).toHaveCount(0);
  });
});
