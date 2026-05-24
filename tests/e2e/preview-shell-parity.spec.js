// @ts-check
/**
 * Preview shell 100x — manager Lane 2 + tenant hero probes (batch 1483–1485).
 * Requires Django on manager.runmycampus.com:${VISUAL_QA_PORT:-8012}
 * and demo-school tenant host for role-home checks.
 */
const { test, expect } = require('@playwright/test');
const {
  ensureManagerHost,
  ensureManagerSession,
  MANAGER_BASE_URL,
  AUTH_STATE_PATH,
} = require('./helpers/manager-login');

const MANAGER_HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const MANAGER_PORT = process.env.VISUAL_QA_PORT || '8012';
const MANAGER_BASE =
  process.env.MANAGER_BASE_URL || `http://${MANAGER_HOST}:${MANAGER_PORT}`;
const TENANT_HOST = process.env.VISUAL_QA_TENANT_HOST || 'demo-school.runmycampus.com';
const TENANT_BASE =
  process.env.TENANT_BASE_URL || `http://${TENANT_HOST}:${MANAGER_PORT}`;

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

test.describe('Preview shell parity — manager', () => {
  test.use({ storageState: AUTH_STATE_PATH });

  test.beforeEach(async ({ page }) => {
    await ensureManagerSession(page);
    await ensureManagerHost(page, MANAGER_BASE);
  });

  for (const vp of VIEWPORTS) {
    test(`super landing header order @ ${vp.width}px`, async ({ page }) => {
      await page.setViewportSize(vp);
      await page.goto(`${MANAGER_BASE}/super/`, { waitUntil: 'domcontentloaded' });
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
    await page.goto(`${MANAGER_BASE}/super/schools/`, {
      waitUntil: 'domcontentloaded',
    });
    await assertHealthyShell(page);
    await expect(page.locator('[data-rmc-scroll-policy="paginate"]')).toBeVisible();
    await expect(
      page.locator('.rmc-data-table, table.table-family')
    ).toBeVisible();
    const pager = page.locator('nav.rmc-pagination, nav[aria-label*="Schools"]');
    const pagerCount = await pager.count();
    if (pagerCount > 0) {
      await expect(pager.first()).toBeVisible();
    }
    await assertNoHorizontalOverflow(page);
  });

  test('offboarding queue paginate policy', async ({ page }) => {
    await page.goto(`${MANAGER_BASE}/super/offboarding/`, {
      waitUntil: 'domcontentloaded',
    });
    await assertHealthyShell(page);
    await expect(page.locator('[data-rmc-scroll-policy="paginate"]')).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });
});

test.describe('Preview shell parity — tenant role home', () => {
  test('teacher dashboard hero greeting when session available', async ({ page }) => {
    const loginUrl = `${TENANT_BASE}/t/demo-school/authentication/login/`;
    let navigated = false;
    try {
      await page.goto(loginUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
      navigated = true;
    } catch (err) {
      test.skip(true, `tenant host unavailable: ${err.message}`);
    }
    if (!navigated) return;
    const onLogin = (await page.locator('input[name="username"]').count()) > 0;
    if (!onLogin) {
      await page.goto(`${TENANT_BASE}/portal/teacher/`, {
        waitUntil: 'domcontentloaded',
      });
      const hero = page.locator('[data-rmc-tp-hero-greeting="1"]');
      if ((await hero.count()) > 0) {
        await expect(hero).toBeVisible();
        await assertNoHorizontalOverflow(page);
      }
      return;
    }
    const teacherUser = process.env.VISUAL_QA_TEACHER_USERNAME || 'teacher';
    const teacherPass = process.env.VISUAL_QA_TEACHER_PASSWORD || 'Test1234';
    await page.locator('input[name="username"]').fill(teacherUser);
    await page.locator('input[name="password"]').fill(teacherPass);
    const roleSelect = page.locator('select[name="role"]');
    if (await roleSelect.count()) {
      await roleSelect.selectOption('teacher');
    }
    await page.getByRole('button', { name: /log in/i }).click();
    await page.waitForURL(
      (url) => !/\/authentication\/login\/?$/i.test(url.pathname),
      { timeout: 90000, waitUntil: 'domcontentloaded' }
    );
    await page.goto(`${TENANT_BASE}/portal/teacher/`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('[data-rmc-tp-hero-greeting="1"]')).toBeVisible({
      timeout: 15000,
    });
    await assertNoHorizontalOverflow(page);
  });
});
