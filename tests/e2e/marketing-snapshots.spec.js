// @ts-check
/**
 * Marketing visual-regression snapshots (desktop). Baselines live beside this file.
 * Run: bash scripts/run_marketing_snapshots.sh
 * Update baselines: UPDATE_SNAPSHOTS=1 bash scripts/run_marketing_snapshots.sh
 */
const { test, expect } = require('@playwright/test');

const MARKETING_BASE_URL =
  process.env.MARKETING_BASE_URL ||
  process.env.BASE_URL ||
  'http://runmycampus.com:8012';

test.use({ baseURL: MARKETING_BASE_URL });

const SNAPSHOT_PAGES = [
  { path: '/', name: 'home' },
  { path: '/pricing/', name: 'pricing' },
  { path: '/contact/', name: 'contact' },
];

test.describe('marketing snapshots @desktop', () => {
  for (const { path, name } of SNAPSHOT_PAGES) {
    test(`snapshot ${name}`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 });
      await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(500);
      await expect(page).toHaveScreenshot(`${name}-1280.png`, {
        fullPage: true,
        maxDiffPixelRatio: 0.02,
      });
    });
  }
});
