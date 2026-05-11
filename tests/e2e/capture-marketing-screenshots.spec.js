// @ts-check
/**
 * One-off screenshot capture so the engineer can actually look at the
 * marketing pages instead of styling blind. Saves PNGs to .tmp/screens/.
 */
const { test, expect } = require('@playwright/test');
const path = require('path');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8000';
test.use({ baseURL: BASE_URL });

const OUT = path.resolve(__dirname, '..', '..', '.tmp', 'screens');

const PAGES = [
  { path: '/v2/', name: 'home' },
  { path: '/platform/', name: 'platform' },
  { path: '/platform/admissions/', name: 'platform-admissions' },
  { path: '/pricing/', name: 'pricing' },
  { path: '/trust/', name: 'trust' },
  { path: '/contact/', name: 'contact' },
];

const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];

test.describe.configure({ mode: 'serial' });

for (const vp of VIEWPORTS) {
  test.describe(`viewport: ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    for (const p of PAGES) {
      test(`${p.name}`, async ({ page }) => {
        await page.goto(p.path, { waitUntil: 'domcontentloaded', timeout: 30000 });
        // Force-reveal every scroll-reveal element so screenshots are
        // deterministic. The motion JS has a 2.5s safety fallback; in tests
        // we just opt out of motion entirely for repeatable captures.
        await page.evaluate(() => {
          document.querySelectorAll('[data-mkt-reveal], [data-mkt-reveal-stagger]').forEach((el) => {
            el.classList.add('is-revealed');
          });
        });
        await page.waitForTimeout(400);
        const file = path.join(OUT, `${p.name}-${vp.name}.png`);
        await page.screenshot({ path: file, fullPage: true });
        expect(true).toBeTruthy();
      });
    }
  });
}
