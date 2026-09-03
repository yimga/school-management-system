// @ts-check
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8000';

test.use({ baseURL: MARKETING_BASE_URL });

const VIEWPORTS = {
  desktop: { width: 1280, height: 720 },
  mobile: { width: 390, height: 844 },
};

const ACCESSIBILITY_PATHS = [
  '/',
  '/platform/',
  '/platform/admissions/',
  '/platform/fees-payments/',
  '/platform/parent-portal/',
  '/platform/teacher-portal/',
  '/platform/analytics/',
  '/platform/security/',
  '/solutions/private-schools/',
  '/solutions/international-schools/',
  '/solutions/multi-campus/',
  '/solutions/faith-based-schools/',
  '/solutions/growing-school-networks/',
  '/pricing/',
  '/contact/',
  '/demo/',
  '/resources/',
];

async function assertNoWideOverflow(page, label) {
  const delta = await page.evaluate(() => {
    const el = document.documentElement;
    return Math.max(0, el.scrollWidth - el.clientWidth);
  });
  expect.soft(delta, `${label} overflow px=${delta}`).toBeLessThanOrEqual(16);
}

/**
 * The marketing surface fades content in on scroll ([data-mkt-reveal] /
 * .rmc-reveal -> .is-revealed, static/marketing/js/marketing-motion.js and
 * static/js/rmc-reveal.js). A scan that lands mid-fade reports the transient
 * composited colour: this spec was flagging `#fdfbf9 on #faf7f2` at 1.03:1 --
 * text at ~5% opacity over the cream, i.e. text nobody has been shown yet --
 * and it did so only under load, which is what made two runs of the same tree
 * disagree by hundreds of nodes. Wait for the reveal to finish before scanning.
 * Nothing is excluded: an element that is permanently low-contrast is still
 * fully opaque here and is still reported.
 */
async function waitForRevealsToSettle(page) {
  const PENDING = '[data-mkt-reveal]:not(.is-revealed), [data-mkt-reveal-stagger]:not(.is-revealed), .rmc-reveal:not(.is-revealed)';
  // The observers only fire for what has entered the viewport, so walk the page
  // first; marketing-motion.js additionally reveals anything still hidden after
  // 2.5s, which bounds this wait.
  await page.evaluate(async () => {
    const step = Math.max(320, Math.floor(window.innerHeight * 0.8));
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 60));
    }
    window.scrollTo(0, 0);
  });
  await page
    .waitForFunction(
      (sel) => document.querySelectorAll(sel).length === 0,
      PENDING,
      { timeout: 10000 },
    )
    .catch(() => {});
  // One frame past the last class flip so the CSS transition has finished.
  await page.waitForTimeout(600);
}

async function assertNoSeriousOrCriticalAxe(page, label) {
  await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
  await waitForRevealsToSettle(page);
  const { violations } = await new AxeBuilder({ page }).analyze();
  const blocking = violations.filter(
    (violation) => violation.impact === 'critical' || violation.impact === 'serious',
  );
  expect(blocking, `serious/critical axe violations on ${label}`).toEqual([]);
}

test.describe('marketing accessibility', () => {
  for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(`viewport: ${viewportName}`, () => {
      test.use({ viewport });

      for (const path of ACCESSIBILITY_PATHS) {
        test(`${path} has accessible structure and no blocking axe issues`, async ({ page }) => {
          const targetPath = path === '/' ? '/marketing/' : path;
          const response = await page.goto(targetPath, {
            waitUntil: 'domcontentloaded',
            timeout: 45000,
          });

          expect(response).toBeTruthy();
          expect(response.status(), `${path} HTTP`).toBeLessThan(400);
          await expect(page.locator('body')).toBeVisible();
          await expect(page.locator('h1').first()).toBeVisible({ timeout: 15000 });
          await assertNoWideOverflow(page, `${viewportName} ${path}`);
          await assertNoSeriousOrCriticalAxe(page, `${viewportName} ${path}`);
        });
      }
    });
  }

  test.describe('forms and navigation accessibility', () => {
    test.use({ viewport: VIEWPORTS.desktop });

    test('contact form controls expose accessible names', async ({ page }) => {
      await page.goto('/contact/', { waitUntil: 'domcontentloaded', timeout: 45000 });
      await expect(page.locator('#contact-name')).toBeVisible();
      await expect(page.locator('#contact-email')).toBeVisible();
      await expect(page.locator('#contact-inquiry-type')).toBeVisible();
      await expect(page.locator('#contact-message')).toBeVisible();
      await expect(page.locator('#contact-name')).toHaveAccessibleName(/name/i);
      await expect(page.locator('#contact-email')).toHaveAccessibleName(/email/i);
      await expect(page.locator('#contact-inquiry-type')).toHaveAccessibleName(/inquiry type/i);
      await expect(page.locator('#contact-message')).toHaveAccessibleName(/message/i);
    });

    test('demo form controls expose accessible names', async ({ page }) => {
      await page.goto('/demo/', { waitUntil: 'domcontentloaded', timeout: 45000 });
      const controls = [
        ['#demo-name', /name/i],
        ['#demo-email', /email/i],
        ['#demo-phone', /phone/i],
        ['#demo-school', /school or organization/i],
        ['#demo-country', /country/i],
        ['#demo-school-type', /school type/i],
        ['#demo-student-count', /approximate student count/i],
        ['#demo-message', /message/i],
      ];
      for (const [selector, name] of controls) {
        await expect(page.locator(selector)).toBeVisible();
        await expect(page.locator(selector)).toHaveAccessibleName(name);
      }
    });

    test('mega menu can open from keyboard focus', async ({ page }) => {
      await page.goto('/marketing/', { waitUntil: 'domcontentloaded', timeout: 45000 });
      const platformToggle = page.locator('#mktNavDd1');
      await platformToggle.focus();
      await expect(platformToggle).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(page.locator('#marketingNav .mkt-mega-menu').first()).toBeVisible({
        timeout: 5000,
      });
      await expect(page.locator('#marketingNav .mkt-mega-menu a').first()).toBeVisible();
    });
  });
});
