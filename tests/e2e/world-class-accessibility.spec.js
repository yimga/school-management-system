// @ts-check
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SKIP_AXE = process.env.SKIP_AXE === '1';
const HAS_AUTH = process.env.WORLD_CLASS_AUTH === '1';

test.use({ baseURL: BASE_URL });

const ROUTES = [
  '/marketing/',
  '/resources/product-tour/',
  '/pricing/',
  '/trust/',
  '/demo/',
  '/super/',
  '/configuration/',
  '/configuration/blueprints/',
  '/configuration/workflow-packs/',
  '/configuration/change-requests/',
  '/configuration/registries/health/',
  '/school/settings/',
  '/school/setup/blueprints/',
  '/school/setup/packs/',
  '/school/setup/imports/',
  '/school/money/',
  '/school/offline/',
  '/school/audit/',
  '/school/security/',
];

const VIEWPORTS = {
  desktop: { width: 1366, height: 768 },
  mobile: { width: 390, height: 844 },
};

const PROTECTED_PREFIXES = ['/super/', '/configuration/', '/school/'];

function isProtected(route) {
  return PROTECTED_PREFIXES.some((prefix) => route.startsWith(prefix));
}

async function assertNoWideOverflow(page, label) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect.soft(overflow, `${label} horizontal overflow`).toBeLessThanOrEqual(16);
}

async function assertAxe(page, label) {
  if (SKIP_AXE) return;
  const { violations } = await new AxeBuilder({ page }).analyze();
  const blocking = violations.filter((violation) => violation.impact === 'critical' || violation.impact === 'serious');
  expect(blocking, `serious/critical axe violations on ${label}`).toEqual([]);
}

test.describe('world-class accessibility route smoke', () => {
  for (const [viewportName, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(viewportName, () => {
      test.use({ viewport });

      for (const route of ROUTES) {
        test(`${route} has headings, named actions, no overflow, and axe path`, async ({ page }) => {
          const response = await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 45000 });
          expect(response).toBeTruthy();
          expect(response.status()).toBeLessThan(500);
          await expect(page.locator('body')).toBeVisible();
          if (isProtected(route) && !HAS_AUTH) {
            await expect(page.locator('body')).toContainText(/sign in|log in|login|access/i);
            return;
          }
          await expect(page.locator('h1, [data-world-class-page-hero]').first()).toBeVisible({ timeout: 15000 });
          await expect(page.locator('a[href="#"], button:empty')).toHaveCount(0);
          await assertNoWideOverflow(page, `${viewportName} ${route}`);
          await assertAxe(page, `${viewportName} ${route}`);
        });
      }
    });
  }
});
