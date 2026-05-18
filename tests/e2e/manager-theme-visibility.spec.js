// @ts-check
/**
 * Manager theme visibility: Light / Dark / System must keep #cp-main-content readable.
 * Requires Django on manager host with visual QA credentials (see manager-surface-parity.spec.js).
 */
const { test, expect } = require('@playwright/test');
const { ensureManagerHost, AUTH_STATE_PATH } = require('./helpers/manager-login');

const MANAGER_HOST = process.env.VISUAL_QA_MANAGER_HOST || 'manager.runmycampus.com';
const MANAGER_PORT = process.env.VISUAL_QA_PORT || '8012';
const MANAGER_BASE_URL =
  process.env.MANAGER_BASE_URL ||
  process.env.BASE_URL ||
  `http://${MANAGER_HOST}:${MANAGER_PORT}`;

const MANAGER_USERNAME = process.env.VISUAL_QA_USERNAME || 'visualqa_admin';
const MANAGER_PASSWORD = process.env.VISUAL_QA_PASSWORD || 'VisualQaPass123!';

const THEME_KEY = 'runmycampus-theme-preference';

test.use({
  baseURL: MANAGER_BASE_URL,
  viewport: { width: 1400, height: 900 },
});

/** @param {import('@playwright/test').Page} page */
async function setThemePreference(page, pref) {
  await page.evaluate(
    ({ key, preference }) => {
      localStorage.setItem(key, preference);
      if (window.RMCTheme && typeof window.RMCTheme.set === 'function') {
        window.RMCTheme.set(preference);
      } else {
        document.documentElement.setAttribute('data-theme', preference);
        const resolved =
          preference === 'system'
            ? window.matchMedia('(prefers-color-scheme: dark)').matches
              ? 'dark'
              : 'light'
            : preference;
        document.documentElement.setAttribute('data-resolved-theme', resolved);
        document.documentElement.setAttribute('data-bs-theme', resolved);
        document.documentElement.classList.toggle('dark', resolved === 'dark');
      }
    },
    { key: THEME_KEY, preference: pref }
  );
}

/** Relative luminance 0–1 from rgb(). */
function luminance(rgb) {
  const m = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!m) return null;
  const [r, g, b] = [m[1], m[2], m[3]].map((v) => {
    const c = Number(v) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** @param {import('@playwright/test').Page} page */
async function mainContentRoot(page) {
  const main = page
    .locator('#cp-main-content, [data-rmc-shell-main="django-admin"], #content')
    .first();
  await expect(main).toBeAttached({ timeout: 30000 });
  await expect(main).toBeVisible({ timeout: 30000 });
  return main;
}

/** @param {import('@playwright/test').Page} page */
async function assertMainReadable(page) {
  const main = await mainContentRoot(page);
  const sample = main.locator('h1, h2, .results, table, .module, p').first();
  const target = (await sample.count()) > 0 ? sample : main;
  const fg = await target.evaluate((el) => getComputedStyle(el).color);
  const bg = await main.evaluate((el) => getComputedStyle(el).backgroundColor);
  const fgL = luminance(fg);
  const bgL = luminance(bg);
  expect(fgL, `foreground ${fg}`).not.toBeNull();
  expect(bgL, `background ${bg}`).not.toBeNull();
  if (fgL !== null && bgL !== null) {
    const contrast = (Math.max(fgL, bgL) + 0.05) / (Math.min(fgL, bgL) + 0.05);
    expect(contrast, `contrast ratio fg=${fg} bg=${bg}`).toBeGreaterThan(2.5);
  }
}

test.describe('manager theme visibility (authenticated)', () => {
  test.describe.configure({ mode: 'serial', timeout: 120000 });

  test.use({
    storageState: AUTH_STATE_PATH,
  });

  test.beforeEach(async ({ page }) => {
    await ensureManagerHost(page);
    await page.goto('/admin/schools/school/', {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    await ensureManagerHost(page);
    await mainContentRoot(page);
  });

  for (const pref of ['light', 'dark', 'system']) {
    test(`admin index readable: ${pref}`, async ({ page }) => {
      await page.goto('/admin/', {
        waitUntil: 'domcontentloaded',
        timeout: 60000,
      });
      await ensureManagerHost(page);
      await setThemePreference(page, pref);
      const index = page.locator('.cp-admin-index');
      await expect(index).toBeVisible({ timeout: 30000 });
      await expect(index).toContainText(/Platform Backoffice/i);
      const box = await index.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThan(120);
      await assertMainReadable(page);
    });

    test(`admin changelist readable: ${pref}`, async ({ page }) => {
      await setThemePreference(page, pref);
      const resolved = await page.evaluate(() =>
        document.documentElement.getAttribute('data-resolved-theme')
      );
      expect(resolved === 'light' || resolved === 'dark').toBeTruthy();
      await expect(page.locator('html')).toHaveAttribute('data-theme', pref);
      if (resolved === 'dark') {
        await expect(page.locator('html')).toHaveClass(/dark/);
      }
      await assertMainReadable(page);
    });
  }
});
