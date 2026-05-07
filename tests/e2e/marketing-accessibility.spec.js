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

async function assertNoSeriousOrCriticalAxe(page, label) {
  await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
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
