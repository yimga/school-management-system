// @ts-check
/**
 * Smoke + a11y for the editorial homepage (served at both / and /v2/).
 *
 * As of the Phase 4 cutover (2026-05-10), the marketing_landing view renders
 * marketing_landing_v2.html — the editorial cream/serif/terracotta page is
 * the production homepage. /v2/ remains as a preview alias with `noindex`,
 * so reviewers can deep-link without competing with / for SEO.
 *
 * The page now uses the inherited (editorial-restyled) marketing_header.html
 * and marketing_footer.html — earlier hide-the-dark-chrome rules have been
 * removed. The body carries data-mkt-edition="editorial" so tokens-editorial.css
 * activates. Assertions reflect this state.
 *
 * Run:
 *   MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8000
 *   npx playwright test tests/e2e/marketing-v2-smoke.spec.js
 */
const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8000';

test.use({ baseURL: MARKETING_BASE_URL });

let AxeBuilder = null;
try {
  AxeBuilder = require('@axe-core/playwright').default;
} catch (_) {
  /* run `npm install` after adding @axe-core/playwright */
}

const SKIP_AXE = process.env.SKIP_AXE === '1';

const VIEWPORTS = {
  desktop: { width: 1280, height: 720 },
  tablet: { width: 834, height: 1112 },
  mobile: { width: 390, height: 844 },
};

async function assertNoWideOverflow(page) {
  const delta = await page.evaluate(() => {
    const el = document.documentElement;
    return Math.max(0, el.scrollWidth - el.clientWidth);
  });
  expect.soft(delta, `overflow px=${delta}`).toBeLessThanOrEqual(16);
}

async function scanAxe(page, label) {
  if (SKIP_AXE || !AxeBuilder) {
    test.info().annotations.push({
      type: 'axe',
      description: SKIP_AXE ? 'SKIP_AXE=1' : 'install @axe-core/playwright',
    });
    return;
  }
  await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
  const { violations } = await new AxeBuilder({ page }).analyze();
  const critical = violations.filter((v) => v.impact === 'critical');
  expect.soft(critical, `axe critical violations on ${label}`).toEqual([]);
}

test.describe('editorial /v2 preview', () => {
  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(`viewport: ${vpName}`, () => {
      test.use({ viewport });

      test('renders editorial chrome and content', async ({ page }) => {
        const jsErrors = [];
        page.on('pageerror', (e) => jsErrors.push(e.message));

        const res = await page.goto('/v2/', {
          waitUntil: 'domcontentloaded',
          timeout: 45000,
        });
        expect(res).toBeTruthy();
        expect(res.status(), '/v2 HTTP').toBeLessThan(400);

        // Body carries the editorial flag — without it, tokens-editorial.css
        // selectors don't match the inherited marketing chrome.
        await expect(page.locator('body[data-mkt-edition="editorial"]')).toHaveCount(1);

        // Inherited marketing chrome renders (now editorial-restyled).
        // On mobile/tablet the nav collapses to a hamburger; check presence
        // in the DOM rather than visibility.
        await expect(page.locator('nav.mkt-navbar')).toHaveCount(1);
        await expect(page.locator('footer.mkt-footer')).toBeVisible();

        // Dieted primary nav: 4 items present in the DOM (visibility depends
        // on viewport — Bootstrap collapses below lg breakpoint).
        for (const item of ['Platform', 'Solutions', 'Pricing', 'Resources']) {
          await expect(
            page.locator('nav.mkt-navbar').getByText(item, { exact: true }).first(),
          ).toHaveCount(1);
        }

        // Dieted footer: 4 columns (Product / Customers / Resources / Company)
        // each rendered as an h4 inside a .mkt-footer-section block.
        for (const col of ['Product', 'Customers', 'Resources', 'Company']) {
          await expect(
            page.locator(`footer.mkt-footer h4:text-is("${col}")`),
          ).toHaveCount(1);
        }

        // Hero, jobs, close-CTA editorial copy renders.
        await expect(page.getByRole('heading', { level: 1 })).toContainText(
          /run your school the way your school actually runs/i,
        );
        await expect(page.getByText(/less software\. more school\./i)).toBeVisible();

        // Five-jobs section: each row eyebrow lives in main content. Scope to
        // <main> so we don't pick up mega-menu items in the nav (which match
        // strings like "Teachers & academics" but stay hidden on closed
        // dropdowns / collapsed mobile nav).
        for (const role of [
          'School leaders',
          'Teachers',
          'Parents',
          'Finance',
          'IT & operations',
        ]) {
          await expect(
            page.locator('main').getByText(role, { exact: false }).first(),
          ).toBeVisible();
        }

        await assertNoWideOverflow(page);
        await scanAxe(page, `/v2 ${vpName}`);
        expect(jsErrors, `JS errors on /v2 ${vpName}`).toEqual([]);
      });
    });
  }

  test('/v2/ preview is noindex', async ({ page }) => {
    await page.goto('/v2/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    const robots = await page
      .locator('meta[name="robots"]')
      .getAttribute('content');
    expect(robots || '').toMatch(/noindex/i);
  });

  test('production homepage marketing_landing is indexable and editorial', async ({ request }) => {
    // After Phase 4 cutover, marketing_landing renders the same editorial
    // template as /v2/ but without the noindex meta. Use the request fixture
    // (raw HTTP, no browser navigation) so we don't fight chromium's
    // host-resolver setup — manual curl confirms /marketing/ returns 200
    // in ~250ms; this matches that without the navigation overhead.
    const u = new URL(MARKETING_BASE_URL);
    const port = u.port || '8000';
    const res = await request.get(`http://127.0.0.1:${port}/marketing/`, {
      headers: { Host: 'runmycampus.com' },
    });
    expect(res.status()).toBe(200);
    const html = await res.text();
    expect(html).toMatch(/data-mkt-edition="editorial"/);
    expect(html).toMatch(/Run every school day from one operating system/i);
    // Production homepage must NOT carry noindex (only /v2/ preview does).
    expect(html).not.toMatch(/<meta\s+name=["']robots["'][^>]*noindex/i);
  });

  test('book-demo CTA links to /demo/', async ({ page }) => {
    await page.goto('/v2/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    const cta = page.getByRole('link', { name: /book a demo/i }).first();
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute('href', /\/demo\/?$/);
  });
});
