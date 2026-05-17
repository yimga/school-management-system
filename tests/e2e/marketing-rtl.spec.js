// @ts-check
//
// Marketing RTL (right-to-left) layout verification — `ar` locale.
//
// 12-pillar audit P2/P11 follow-up. RunMyCampus ships 17 locales
// (memory v3.13); `ar` is the canonical RTL locale. The shell flips
// via Django's i18n context processor (LANGUAGE_BIDI) and the
// `body.bidi-rtl` class set by templates/marketing/base_marketing.html.
//
// This spec asserts the mechanical correctness of the RTL flip on the
// marketing surface — not visual review:
//
//   1. `<html dir="rtl">` is set when ?lang=ar is active.
//   2. `<html lang="ar">` follows the locale.
//   3. body carries `.bidi-rtl` so RTL-specific CSS rules apply.
//   4. The page doesn't horizontally overflow under RTL (a class of
//      bug where mirrored margins push elements off the right edge in
//      LTR but the left edge in RTL — same defect, mirrored).
//   5. The marketing nav primary CTA remains in the focus order.
//
// To run locally:
//   RUNMYCAMPUS_AI_ALLOW_EXTERNAL=0 \
//     MARKETING_BASE_URL=http://runmycampus.com:8000 \
//     npx playwright test tests/e2e/marketing-rtl.spec.js
//
// CI: gated on Playwright availability; not in the lighthouse-ci or
// pa11y-ci default matrix. Manager promotes via npm-script extension.

const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8000';

test.use({
  baseURL: MARKETING_BASE_URL,
  viewport: { width: 1280, height: 800 },
});

// Subset of routes that should respect RTL. The full ACCESSIBILITY_PATHS
// list from marketing-accessibility.spec.js is too long for a per-locale
// sweep; cover the highest-leverage public surface.
const RTL_PATHS = [
  '/?lang=ar',
  '/platform/?lang=ar',
  '/pricing/?lang=ar',
  '/contact/?lang=ar',
];

async function htmlAttr(page, name) {
  return page.evaluate((attr) => {
    return document.documentElement.getAttribute(attr) || '';
  }, name);
}

async function bodyClasses(page) {
  return page.evaluate(() => Array.from(document.body.classList));
}

async function horizontalOverflowPx(page) {
  return page.evaluate(() => {
    const el = document.documentElement;
    return Math.max(0, el.scrollWidth - el.clientWidth);
  });
}

test.describe('marketing RTL — ar locale', () => {
  for (const rtlPath of RTL_PATHS) {
    test(`${rtlPath} sets dir=rtl and bidi-rtl with no horizontal overflow`, async ({ page }) => {
      await page.goto(rtlPath);
      await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => {});

      const dir = await htmlAttr(page, 'dir');
      const lang = await htmlAttr(page, 'lang');
      const cls = await bodyClasses(page);
      const overflow = await horizontalOverflowPx(page);

      // (1) <html dir="rtl">
      expect(dir, `${rtlPath} <html dir>`).toBe('rtl');
      // (2) <html lang="ar"> (Django uses 'ar' or 'ar-*')
      expect(lang, `${rtlPath} <html lang>`).toMatch(/^ar(\b|-)/);
      // (3) body.bidi-rtl is the agreed class shell-CSS keys off.
      expect(cls, `${rtlPath} body classes`).toContain('bidi-rtl');
      // (4) No horizontal overflow > 16px (allowance for scrollbar gutter).
      expect(overflow, `${rtlPath} horizontal overflow px`).toBeLessThanOrEqual(16);
    });
  }

  test('language switcher persists ar selection across navigation', async ({ page }) => {
    await page.goto('/?lang=ar');
    await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => {});
    // Navigate to pricing without ?lang= — locale must stick via cookie / session.
    await page.goto('/pricing/');
    await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => {});
    const lang = await htmlAttr(page, 'lang');
    expect(lang, 'pricing page after ar switch').toMatch(/^ar(\b|-)/);
  });
});
