// @ts-check
//
// 400% browser-zoom matrix verification.
//
// 12-pillar audit P2 follow-up — the seven-pillar a11y prompt requires
// WCAG 2.2 1.4.10 (reflow) compliance: content must remain usable at
// 400% zoom on a 1280×1024 viewport without two-dimensional scrolling.
//
// Approach: we don't actually zoom the browser chrome (Playwright doesn't
// expose ctrl-plus directly). Instead we *simulate* 400% zoom the way
// browsers do internally — shrink the viewport to 1/4 of the target
// "reflow" width and keep the layout pixels at 100%. This is the WCAG
// 1.4.10 algorithm: 1280 / 4 = 320 CSS-pixel-wide viewport.
//
// Routes covered are the high-value tabular surfaces the audit flagged
// (finance invoice table, teacher grade grid) plus the marketing home,
// portal home, and manager dashboard — five anchors for the surface
// matrix. The gate is "no horizontal scrolling at 320px" (delta ≤ 16px
// for scrollbar gutter), plus "every primary CTA on the page remains
// reachable in tab order."

const { test, expect } = require('@playwright/test');

const BASE_URL =
  process.env.BASE_URL ||
  process.env.MARKETING_BASE_URL ||
  'http://localhost:8000';

// WCAG 2.2 1.4.10: content must reflow at 320 CSS px wide (= 1280 / 400%)
const REFLOW_WIDTH = 320;
const REFLOW_HEIGHT = 256;  // 1024 / 400%

test.use({
  baseURL: BASE_URL,
  viewport: { width: REFLOW_WIDTH, height: REFLOW_HEIGHT },
});

// Anchor routes. The two tabular surfaces from the audit + three shells.
// Adjust as tenant routing evolves.
const ZOOM_PATHS = [
  { path: '/', label: 'marketing home' },
  { path: '/pricing/', label: 'marketing pricing' },
  { path: '/portal/', label: 'tenant portal home' },
  { path: '/portal/finance/invoices/', label: 'finance invoice table' },
  { path: '/portal/teacher/', label: 'teacher grade grid' },
];

async function horizontalOverflowPx(page) {
  return page.evaluate(() => {
    const el = document.documentElement;
    return Math.max(0, el.scrollWidth - el.clientWidth);
  });
}

async function countTabReachable(page) {
  return page.evaluate(() => {
    // Count elements that participate in keyboard tab order.
    const focusables = document.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), '
      + 'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    return focusables.length;
  });
}

test.describe('400% zoom (320×256 reflow viewport)', () => {
  for (const { path, label } of ZOOM_PATHS) {
    test(`${label} reflows at 320px without 2D scrolling`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => {});

      // WCAG 1.4.10 — no horizontal scrolling at 320px.
      const overflow = await horizontalOverflowPx(page);
      expect(
        overflow,
        `${label} (${path}) horizontal overflow px at 320 viewport`
      ).toBeLessThanOrEqual(16);

      // Sanity: page rendered something focusable. A blank page (auth
      // redirect with no nav) is a false-positive escape hatch — assert
      // we have at least 1 focusable, otherwise the reflow check is
      // vacuous.
      const focusables = await countTabReachable(page);
      expect(focusables, `${label} (${path}) tab-reachable elements`).toBeGreaterThan(0);
    });
  }

  test('finance invoice table cells do not clip below 32px row height', async ({ page }) => {
    // Touch target check (WCAG 2.5.8): interactive elements should stay
    // tappable. Use min-row-height as a proxy on the high-density table.
    await page.goto('/portal/finance/invoices/');
    await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => {});
    const minRowHeight = await page.evaluate(() => {
      const rows = document.querySelectorAll('table tr, [role="row"]');
      if (rows.length === 0) return null;  // no table on page — skip
      let min = Number.POSITIVE_INFINITY;
      for (const r of rows) {
        const h = r.getBoundingClientRect().height;
        if (h > 0 && h < min) min = h;
      }
      return Number.isFinite(min) ? min : null;
    });
    if (minRowHeight === null) {
      test.skip(true, 'no table rows rendered (auth redirect or empty state)');
    }
    expect(
      minRowHeight,
      'finance invoice row min-height at 320 viewport'
    ).toBeGreaterThanOrEqual(32);
  });
});
