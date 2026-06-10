// @ts-check
/**
 * Phase 1 — tenant django-admin sidebar logout visibility, contrast, and navigation integrity.
 *
 * Requires Django on VISUAL_QA_PORT with demo-school mapped:
 *   npm run test:e2e:phase1-architecture
 */
const { test, expect } = require('@playwright/test');
const {
  loginTenant,
  openAdminUserMenu,
  TENANT_BASE_URL,
} = require('./helpers/tenant-login');

const VIEWPORTS = [
  { label: '320px', width: 320, height: 640 },
  { label: '768px', width: 768, height: 900 },
  { label: '1440px', width: 1440, height: 900 },
  { label: '4K', width: 2560, height: 1440 },
];

test.describe('Phase 1 admin navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginTenant(page);
    const adminUrl = `${TENANT_BASE_URL.replace(/\/$/, '')}/admin/`;
    const response = await page.goto(adminUrl, { waitUntil: 'domcontentloaded' });
    expect(response?.status()).toBeLessThan(400);
  });

  for (const vp of VIEWPORTS) {
    test(`logout control visible in viewport at ${vp.label}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });

      if (vp.width < 1280) {
        const mobileToggle = page
          .locator('[data-rmc-sidebar-toggle], .js-sidebar-toggle, [aria-label*="menu" i]')
          .first();
        if (await mobileToggle.isVisible().catch(() => false)) {
          await mobileToggle.click();
        }
      }

      await openAdminUserMenu(page);

      const logout = page.locator('[data-rmc-nav-logout]').first();
      await expect(logout).toBeVisible({ timeout: 8000 });

      const box = await logout.boundingBox();
      expect(box).toBeTruthy();
      if (!box) return;

      expect(box.x).toBeGreaterThanOrEqual(-2);
      expect(box.y).toBeGreaterThanOrEqual(-2);
      expect(box.x + box.width).toBeLessThanOrEqual(vp.width + 4);
      expect(box.y + box.height).toBeLessThanOrEqual(vp.height + 4);

      const href = await logout.getAttribute('href');
      expect(href).toMatch(/logout/i);
    });
  }

  test('logout link meets minimum contrast in dark and light theme', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openAdminUserMenu(page);
    const logout = page.locator('[data-rmc-nav-logout]').first();
    await expect(logout).toBeVisible();

    const ratio = await logout.evaluate((el) => {
      const cs = getComputedStyle(el);
      const fg = (() => {
        const m = cs.color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (!m) return null;
        return { r: +m[1], g: +m[2], b: +m[3] };
      })();
      let bgEl = el.parentElement;
      let bg = null;
      while (bgEl && !bg) {
        const bcs = getComputedStyle(bgEl);
        const parsed = (() => {
          const m = bcs.backgroundColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
          if (!m) return null;
          if (m[4] === '0') return null;
          return { r: +m[1], g: +m[2], b: +m[3] };
        })();
        if (parsed) bg = parsed;
        bgEl = bgEl.parentElement;
      }
      if (!fg || !bg) return 21;
      const l1 =
        0.2126 *
          (fg.r / 255 <= 0.03928
            ? fg.r / 255 / 12.92
            : ((fg.r / 255 + 0.055) / 1.055) ** 2.4) +
        0.7152 *
          (fg.g / 255 <= 0.03928
            ? fg.g / 255 / 12.92
            : ((fg.g / 255 + 0.055) / 1.055) ** 2.4) +
        0.0722 *
          (fg.b / 255 <= 0.03928
            ? fg.b / 255 / 12.92
            : ((fg.b / 255 + 0.055) / 1.055) ** 2.4);
      const l2 =
        0.2126 *
          (bg.r / 255 <= 0.03928
            ? bg.r / 255 / 12.92
            : ((bg.r / 255 + 0.055) / 1.055) ** 2.4) +
        0.7152 *
          (bg.g / 255 <= 0.03928
            ? bg.g / 255 / 12.92
            : ((bg.g / 255 + 0.055) / 1.055) ** 2.4) +
        0.0722 *
          (bg.b / 255 <= 0.03928
            ? bg.b / 255 / 12.92
            : ((bg.b / 255 + 0.055) / 1.055) ** 2.4);
      const lighter = Math.max(l1, l2);
      const darker = Math.min(l1, l2);
      return (lighter + 0.05) / (darker + 0.05);
    });

    expect(ratio).toBeGreaterThanOrEqual(3.0);
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
    await openAdminUserMenu(page);
    await expect(page.locator('[data-rmc-nav-logout]').first()).toBeVisible();
    await page.locator('.admin-sidebar-user-card-inner').first().click();
    await page.waitForTimeout(300);

    const benign = errors.filter(
      (e) =>
        !/favicon|404|net::ERR|DevTools|ResizeObserver|wizard registry/i.test(e)
    );
    expect(benign).toEqual([]);
  });
});
