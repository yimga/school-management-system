// @ts-check
/**
 * Phase 1 — tenant staff backend shell logout visibility, contrast, and navigation integrity.
 *
 * TenantMiddleware redirects /admin/ → /authentication/backend/ (single staff entry).
 * Requires Django on VISUAL_QA_PORT with demo-school mapped:
 *   npm run test:e2e:phase1-architecture
 */
const { test, expect } = require('@playwright/test');
const {
  loginTenant,
  openTenantUserMenu,
  TENANT_BASE_URL,
} = require('./helpers/tenant-login');

const VIEWPORTS = [
  { label: '320px', width: 320, height: 640 },
  { label: '768px', width: 768, height: 900 },
  { label: '1440px', width: 1440, height: 900 },
  { label: '4K', width: 2560, height: 1440 },
];

test.describe('Phase 1 tenant staff navigation', () => {
  test.describe.configure({ timeout: 180000 });

  test.beforeEach(async ({ page }) => {
    await loginTenant(page);
    const adminUrl = `${TENANT_BASE_URL.replace(/\/$/, '')}/admin/`;
    const response = await page.goto(adminUrl, { waitUntil: 'domcontentloaded' });
    expect(response?.status()).toBeLessThan(400);
    await page.waitForURL(/\/authentication\/backend\/?(\?|$|#)/, { timeout: 30000 });
  });

  for (const vp of VIEWPORTS) {
    test(`logout control visible in viewport at ${vp.label}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });

      await openTenantUserMenu(page);

      const logout = page.locator('[data-rmc-nav-logout]').first();
      await expect(logout).toBeVisible({ timeout: 8000 });
      await logout.scrollIntoViewIfNeeded();
      await expect(logout).toBeInViewport({ timeout: 8000 });

      const box = await logout.boundingBox();
      expect(box).toBeTruthy();
      if (!box) return;

      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(vp.width + 2);

      const href = await logout.getAttribute('href');
      expect(href).toMatch(/logout/i);
    });
  }

  test('logout link exposes navigation contract markers', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openTenantUserMenu(page);
    const logout = page.locator('[data-rmc-nav-logout]').first();
    await expect(logout).toBeVisible();
    await expect(logout).toHaveAttribute('href', /logout/i);
    const className = (await logout.getAttribute('class')) || '';
    expect(className).toMatch(/text-danger|text-font-default/);
  });

  test('header navigation anchors resolve without hash dead links', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const deadHashes = await page.evaluate(() => {
      const anchors = Array.from(document.querySelectorAll('a[href="#"]'));
      return anchors
        .filter((a) => !a.getAttribute('data-bs-toggle') && !a.dataset.confirmHref)
        .map((a) => a.outerHTML.slice(0, 120));
    });
    expect(deadHashes).toEqual([]);
  });

  test('no console errors during dropdown open cycle', async ({ page }) => {
    const errors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', (err) => errors.push(String(err)));

    await page.setViewportSize({ width: 768, height: 900 });
    await openTenantUserMenu(page);
    await expect(page.locator('[data-rmc-nav-logout]').first()).toBeVisible();
    const menuTrigger = page.locator('#userDropdownBtn, .admin-sidebar-user-card-inner').first();
    await menuTrigger.click();
    await page.waitForTimeout(300);

    const benign = errors.filter(
      (e) =>
        !/favicon|404|net::ERR|DevTools|ResizeObserver|wizard registry|csp-report|security\/csp/i.test(
          e,
        )
    );
    expect(benign).toEqual([]);
  });
});
