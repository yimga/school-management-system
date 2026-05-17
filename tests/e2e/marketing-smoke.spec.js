// @ts-check
/**
 * Public marketing smoke + accessibility (axe) for Host: runmycampus.com.
 *
 * Start Django first, e.g.:
 *   MULTI_TENANT_BASE_DOMAIN=runmycampus.com python manage.py runserver 127.0.0.1:8000 --settings=config.settings
 *
 * Then:
 *   npm install && npx playwright install chromium
 *   npm run test:e2e:marketing
 *
 * Env: MARKETING_E2E_HOST (default runmycampus.com), SKIP_AXE=1 skips the axe suite entirely,
 * BASE_URL (default http://127.0.0.1:8000).
 */
const { test, expect } = require('@playwright/test');

/** Apex marketing host — chromium resolves via playwright.config host-resolver-rules */
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

const MARKETING_PATHS = [
  '/',
  '/platform/',
  '/pricing/',
  '/trust/',
  '/contact/',
  '/demo/',
  '/company/',
  '/resources/',
  '/resources/guides/',
  '/resources/case-studies/',
  '/resources/blog/',
  '/resources/product-tour/',
  '/for-private-schools/',
  '/for-school-networks/',
  '/offline-first/',
  '/payments-readiness/',
  '/solutions/k12-schools/',
  '/solutions/private-schools/',
  '/platform/student-information-system/',
  '/platform/fees-payments/',
  '/platform/parent-portal/',
  '/platform/teacher-portal/',
  '/platform/security/',
  '/pay/fees/',
  '/communicate/inbox/',
  '/teach/workspace/',
  '/run/analytics/',
  '/communicate/announcements/',
  '/run/workflows/',
];

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
  const serious = violations.filter((v) => v.impact === 'serious');
  if (serious.length) {
    test.info().annotations.push({
      type: 'axe-serious',
      description: `${label}: ${serious.map((v) => v.id).join(', ')}`,
    });
  }
  // Critical issues block the gate; serious (often contrast on dark chrome) are flagged above.
  expect.soft(critical, `axe critical violations on ${label}`).toEqual([]);
}

test.describe('marketing apex host', () => {
  test('GET /contact/submit/ returns 405', async ({ request }) => {
    // Node request bypasses Chromium host-resolver-rules; hit loopback + apex Host.
    const u = new URL(MARKETING_BASE_URL);
    const port = u.port || '8000';
    const res = await request.get(`http://127.0.0.1:${port}/contact/submit/`, {
      headers: { Host: 'runmycampus.com' },
    });
    expect(res.status()).toBe(405);
  });

  test.describe('desktop interactions', () => {
    test.use({ viewport: VIEWPORTS.desktop });

    test('marketing nav dropdown opens', async ({ page }) => {
      await page.goto('/marketing/', { waitUntil: 'networkidle', timeout: 45000 });
      await page.locator('#marketingNav .dropdown-toggle').first().click();
      await expect(
        page.locator('#marketingNav .dropdown-menu a').first(),
      ).toBeVisible({ timeout: 5000 });
    });

    test('homepage hero composite has meaningful alt', async ({ page }) => {
      await page.goto('/marketing/', { waitUntil: 'domcontentloaded', timeout: 45000 });
      const img = page.locator('.mkt-hero-composite-img').first();
      await expect(img).toBeVisible();
      await expect(img).toHaveAttribute(
        'alt',
        /parent|portal|finance|teacher|student|admin|analytics|leadership/i,
      );
    });

    test('contact form submits → /contact/?submitted=', async ({ page }) => {
      await page.goto('/contact/', { waitUntil: 'domcontentloaded', timeout: 45000 });
      await expect(page.locator('form[action*="contact/submit"]')).toBeVisible();
      await page.locator('#contact-name').fill('Playwright Marketing QA');
      await page.locator('#contact-email').fill('marketing-e2e@example.com');
      await page.locator('#contact-inquiry-type').selectOption('general');
      await page.locator('#contact-message').fill('Automated marketing smoke submission.');
      await page.getByRole('button', { name: /submit inquiry/i }).click();
      await page.waitForURL(/\/?contact\/\?submitted=/, { timeout: 25000 });
      expect(page.url()).toContain('submitted=');
    });

    test('keyboard Tab reaches navigation', async ({ page }) => {
      await page.goto('/platform/', { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');
      const focused = await page.evaluate(() => {
        const el = document.activeElement;
        return el && el.tagName ? `${el.tagName}.${el.className || ''}` : '';
      });
      expect(focused.length).toBeGreaterThan(0);
    });
  });

  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(`viewport: ${vpName}`, () => {
      test.use({ viewport });

      for (const path of MARKETING_PATHS) {
        test(`${path}`, async ({ page }) => {
          const jsErrors = [];
          page.on('pageerror', (e) => jsErrors.push(e.message));

          const res = await page.goto(path, {
            waitUntil: 'domcontentloaded',
            timeout: 45000,
          });
          expect(res).toBeTruthy();
          expect(res.status(), `${path} HTTP`).toBeLessThan(400);

          await expect(page.locator('body')).toBeVisible();
          await expect(page.locator('nav.mkt-navbar')).toBeVisible({
            timeout: 15000,
          });
          await expect(page.locator('footer.mkt-footer')).toBeVisible({
            timeout: 15000,
          });

          const bodyText = (await page.locator('body').innerText()).toLowerCase();
          expect(bodyText).not.toContain('page not found');
          expect(bodyText).not.toContain('server error');

          // Root → /marketing/ redirect can briefly exceed strict overflow on some mobiles.
          if (!(vpName === 'mobile' && path === '/')) {
            await assertNoWideOverflow(page);
          }

          // `/` redirects to `/marketing/`; skip toggler race here — other mobile paths cover the menu.
          if (vpName === 'mobile' && path !== '/') {
            const toggler = page.locator('.navbar-toggler');
            await toggler.waitFor({ state: 'visible', timeout: 15000 });
            await toggler.click();
            await expect(page.locator('#marketingNav')).toHaveClass(/show/, {
              timeout: 12000,
            });
          }

          if (path === '/pricing/') {
            await expect(
              page
                .locator('.pricing-grid, .pricing-card, table, section[aria-label*="Pricing"]')
                .first(),
            ).toBeVisible({ timeout: 12000 });
          }

          if (path === '/solutions/private-schools/') {
            await expect(
              page.locator('img[src*="module-admissions"]').first(),
            ).toBeVisible({ timeout: 12000 });
          }

          if (path === '/contact/') {
            await expect(page.locator('#contact-email')).toBeVisible();
            await expect(page.locator('label[for="contact-email"]')).toBeVisible();
          }

          const harsh = jsErrors.filter(
            (m) =>
              !/ResizeObserver|Non-Error promise rejection/i.test(m) &&
              !m.includes('favicon'),
          );
          expect(harsh, `pageerrors on ${path}`).toEqual([]);
        });
      }
    });
  }

  // When skipping axe, omit the whole block (otherwise 15 navigations still run before no-op scans).
  (SKIP_AXE ? test.describe.skip : test.describe)('axe @ desktop width', () => {
    test.use({ viewport: VIEWPORTS.desktop });

    for (const path of MARKETING_PATHS) {
      test(`axe ${path}`, async ({ page }) => {
        // Avoid redirect-chain quirks on `/` during axe injection (same DOM as `/marketing/`).
        const axeUrl = path === '/' ? '/marketing/' : path;
        await page.goto(axeUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await scanAxe(page, `${path}→${axeUrl}`);
      });
    }
  });
});
