// @ts-check
/**
 * Marketing theme matrix: /, /pricing/, /demo/ × light/dark/system × desktop/mobile.
 * Requires Django on runmycampus.com host (see marketing-smoke.spec.js).
 *
 *   npm run test:e2e:marketing:theme
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

const THEME_PATHS = ['/', '/pricing/', '/demo/'];
const THEMES = ['light', 'dark', 'system'];
const VIEWPORTS = {
  desktop: { width: 1280, height: 720 },
  mobile: { width: 390, height: 844 },
};

async function applyThemePreference(page, preference) {
  await page.evaluate((pref) => {
    try {
      localStorage.setItem('rmc-mkt-theme', pref);
    } catch (_) {
      /* ignore */
    }
    const root = document.documentElement;
    root.setAttribute('data-theme-preference', pref);
    let effective = pref;
    if (pref === 'system') {
      effective = window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light';
    }
    root.setAttribute('data-theme', effective);
  }, preference);
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
      for (const theme of THEMES) {
        test(`${vpName} ${path} preference=${theme}`, async ({ page }) => {
          if (theme === 'system') {
            await page.emulateMedia({ colorScheme: 'dark' });
          } else {
            await page.emulateMedia({
              colorScheme: theme === 'dark' ? 'dark' : 'light',
            });
          }

          const res = await page.goto(path, {
            waitUntil: 'domcontentloaded',
            timeout: 45000,
          });
          expect(res).toBeTruthy();
          expect(res.status(), `${path} HTTP`).toBeLessThan(400);

          await applyThemePreference(page, theme);

          const effective = await page.getAttribute('html', 'data-theme');
          expect(['light', 'dark']).toContain(effective);

          const preference = await page.getAttribute('html', 'data-theme-preference');
          expect(preference).toBe(theme);

          await expect(page.locator('nav.mkt-navbar')).toBeVisible({ timeout: 15000 });
          await expect(page.locator('footer.mkt-footer')).toBeVisible({ timeout: 15000 });

          const bodyText = (await page.locator('body').innerText()).toLowerCase();
          expect(bodyText).not.toContain('page not found');

          await scanAxeCritical(page, `${vpName} ${path} ${theme}`);
        });
      }
    }
  }
});
