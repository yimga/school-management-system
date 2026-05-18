// @ts-check
/**
 * Studio OS manager UX waves 1–6 — browser contract on manager host.
 * Requires Django with manager urlconf + superuser (see helpers/manager-login.js).
 *
 * Run: MANAGER_BASE_URL=http://manager.runmycampus.com:8012 \
 *   npx playwright test tests/e2e/studio-os-manager-ux.spec.js --workers=1
 */
const { test, expect } = require('@playwright/test');
const { loginManager, ensureManagerHost } = require('./helpers/manager-login');

const MANAGER_HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const MANAGER_PORT = process.env.VISUAL_QA_PORT || '8012';
const MANAGER_BASE_URL =
  process.env.MANAGER_BASE_URL ||
  process.env.BASE_URL ||
  `http://${MANAGER_HOST}:${MANAGER_PORT}`;

test.use({
  baseURL: MANAGER_BASE_URL,
  viewport: { width: 1440, height: 900 },
});

test.describe('Studio OS manager UX', () => {
  test.beforeEach(async ({ page }) => {
    await loginManager(page);
    await ensureManagerHost(page);
  });

  test('control mode uses focus layout, workspace, and inline feature control', async ({
    page,
  }) => {
    await page.goto('/studio/control/', { waitUntil: 'domcontentloaded', timeout: 90000 });
    await ensureManagerHost(page);

    const layout = page.locator('.cp-layout[data-rmc-studio-focus="1"]');
    await expect(layout).toHaveCount(1);

    await expect(page.locator('[data-rmc-studio-focus-sidebar="1"]')).toHaveCount(1);
    await expect(page.locator('[data-rmc-studio-workspace="1"]')).toHaveCount(1);
    await expect(page.locator('[data-rmc-studio-workspace-main="1"]')).toHaveCount(1);

    const bodyText = await page.locator('body').innerText();
    expect(bodyText).not.toMatch(/Curriculum\s*&\s*region/i);

    const inline = page.locator('[data-rmc-studio-inline-control="1"]');
    if ((await inline.count()) > 0) {
      await expect(page.locator('.feature-control-header')).toHaveCount(0);
      await expect(page.locator('[data-rmc-studio-inline-control-summary="1"]')).toHaveCount(1);
    }
  });

  test('feature control embed is minimal body chrome', async ({ page }) => {
    await page.goto('/siteconfig/feature-control/?embed=1', {
      waitUntil: 'domcontentloaded',
      timeout: 90000,
    });
    await ensureManagerHost(page);

    await expect(page.locator('html[data-rmc-studio-embed="1"]')).toHaveCount(1);
    await expect(page.locator('#studio-embed-main')).toHaveCount(1);
    await expect(page.locator('.portal-sidebar, .cp-layout')).toHaveCount(0);
  });
});
