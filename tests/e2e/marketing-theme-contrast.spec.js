// @ts-check
/**
 * Marketing theme matrix: /, /pricing/, /demo/ × preference × desktop/mobile.
 * Requires Django on runmycampus.com host (see marketing-smoke.spec.js).
 *
 *   npm run test:e2e:marketing:theme
 *
 * WHAT CHANGED ON 2026-09-01, AND WHY IT MATTERED
 * -----------------------------------------------
 * The previous version of this file SET `data-theme` itself, in the page, and
 * then asserted `data-theme` was light or dark. It was asserting its own write:
 * it passed whatever the two theme bootstraps did, including nothing at all.
 *
 * And they were doing something. `mkt-theme-bootstrap.js` defaults an anonymous
 * marketing visitor to light; `theme-preference-bootstrap.js` then ran on the
 * same page, defaulted to "system", resolved that against the OS and overwrote
 * `data-theme`. A first-time visitor whose OS was dark got the dark palette on a
 * surface whose template hardcodes `data-theme="light"` — and a dark axe sweep
 * of that state fails colour-contrast on 56 of 56 pages against 0 in light.
 *
 * So this file now writes only the REAL input — localStorage, or nothing — and
 * asserts what the bootstraps resolved. The unset case is the regression.
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
  /* npm install @axe-core/playwright */
}

const MKT_KEY = 'rmc-mkt-theme';
const THEME_PATHS = ['/', '/pricing/', '/demo/'];
const VIEWPORTS = {
  desktop: { width: 1280, height: 720 },
  mobile: { width: 390, height: 844 },
};

/**
 * Every case runs with the OS in DARK, because dark-OS is the only condition
 * under which the stored preference and the OS disagree — which is where the
 * bug lived. `expected` is what the two bootstraps must resolve between them.
 */
const CASES = [
  {
    stored: null,
    expectedTheme: 'light',
    expectedPreference: 'light',
    why: 'no stored preference: the marketing surface is light-locked, so a dark OS must NOT opt the visitor in',
  },
  {
    stored: 'light',
    expectedTheme: 'light',
    expectedPreference: 'light',
    why: 'explicit light',
  },
  {
    stored: 'dark',
    expectedTheme: 'dark',
    expectedPreference: 'dark',
    why: 'explicit dark still wins — the fix pins the DEFAULT, not the choice',
  },
  {
    stored: 'system',
    expectedTheme: 'dark',
    expectedPreference: 'system',
    why: 'explicit System + dark OS resolves dark, so the toggle keeps working',
  },
];

async function seedPreference(context, stored) {
  await context.addInitScript(
    ({ key, value }) => {
      try {
        if (value === null) {
          localStorage.removeItem(key);
        } else {
          localStorage.setItem(key, value);
        }
      } catch (_) {
        /* private mode — the assertions below will show it */
      }
    },
    { key: MKT_KEY, value: stored },
  );
}

async function scanAxeCritical(page, label) {
  if (!AxeBuilder) {
    test.info().annotations.push({
      type: 'axe',
      description: 'install @axe-core/playwright',
    });
    return;
  }
  await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => {});
  const { violations } = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const critical = violations.filter((v) => v.impact === 'critical');
  expect.soft(critical, `axe critical on ${label}`).toEqual([]);
}

test.describe('marketing theme × contrast matrix', () => {
  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    for (const path of THEME_PATHS) {
      for (const testCase of CASES) {
        const name = testCase.stored === null ? 'unset' : testCase.stored;
        test(`${vpName} ${path} stored=${name}`, async ({ browser }) => {
          const context = await browser.newContext({
            viewport,
            colorScheme: 'dark',
          });
          await seedPreference(context, testCase.stored);
          const page = await context.newPage();
          try {
            const res = await page.goto(path, {
              waitUntil: 'domcontentloaded',
              timeout: 45000,
            });
            expect(res).toBeTruthy();
            expect(res.status(), `${path} HTTP`).toBeLessThan(400);

            // The platform bootstrap re-applies on DOMContentLoaded, so the
            // last word is only in after that has run.
            await page.waitForTimeout(300);

            expect(
              await page.getAttribute('html', 'data-theme'),
              `${path} resolved theme — ${testCase.why}`,
            ).toBe(testCase.expectedTheme);
            expect(
              await page.getAttribute('html', 'data-theme-preference'),
              `${path} preference — ${testCase.why}`,
            ).toBe(testCase.expectedPreference);
            // data-bs-theme and .dark drive different halves of the CSS, and
            // the v3 contract is that all three agree. When they did not, the
            // platform rendered white text on white cards.
            expect(await page.getAttribute('html', 'data-bs-theme')).toBe(
              testCase.expectedTheme,
            );
            expect(
              await page.evaluate(() =>
                document.documentElement.classList.contains('dark'),
              ),
            ).toBe(testCase.expectedTheme === 'dark');

            await expect(page.locator('nav.mkt-navbar')).toBeVisible({ timeout: 15000 });
            await expect(page.locator('footer.mkt-footer')).toBeVisible({ timeout: 15000 });

            const bodyText = (await page.locator('body').innerText()).toLowerCase();
            expect(bodyText).not.toContain('page not found');

            await scanAxeCritical(page, `${vpName} ${path} ${name}`);
          } finally {
            await context.close();
          }
        });
      }
    }
  }
});
