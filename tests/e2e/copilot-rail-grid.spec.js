// @ts-check
/**
 * Copilot rail grid regression — must stay a narrow right column (grid col 3),
 * never a full-width bottom band.
 *
 *   npx playwright test copilot-rail-grid --project=manager-chromium --workers=1
 */
const { test, expect } = require('@playwright/test');
const { ensureManagerSession, MANAGER_BASE_URL } = require('./helpers/manager-login');

const BASE = MANAGER_BASE_URL.replace(/\/$/, '');

test('manager /super/: copilot rail is narrow right column, not bottom band', async ({ page }) => {
  test.setTimeout(120000);
  await ensureManagerSession(page);
  const resp = await page.goto(`${BASE}/super/`, {
    waitUntil: 'domcontentloaded',
    timeout: 90000,
  });
  if (resp && resp.status() >= 400) {
    test.skip(true, `/super/ returned HTTP ${resp.status()}`);
    return;
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  const copilot = page.locator('.rmc-app-shell__copilot').first();
  const count = await copilot.count();
  if (count === 0) {
    test.skip(true, 'copilot rail disabled (cockpit.ai_copilot_rail.enabled=false)');
    return;
  }
  await expect(copilot).toBeVisible({ timeout: 60000 });

  const metrics = await copilot.evaluate((el) => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const shell = el.closest('.rmc-app-shell');
    const shellCols = shell ? getComputedStyle(shell).gridTemplateColumns : '';
    return {
      gridColumn: cs.gridColumn,
      gridRow: cs.gridRow,
      position: cs.position,
      width: r.width,
      height: r.height,
      left: r.left,
      right: r.right,
      top: r.top,
      bottom: r.bottom,
      shellCols,
      vw: document.documentElement.clientWidth,
      vh: document.documentElement.clientHeight,
    };
  });

  // eslint-disable-next-line no-console
  console.log('[copilot-rail-grid]', JSON.stringify(metrics));

  expect(metrics.gridColumn, 'copilot must occupy grid column 3').toMatch(/^3(\s*\/\s*4)?$/);
  expect(metrics.gridRow, 'copilot must share middle row with canvas').toBe('2');
  expect(metrics.width, 'copilot must stay narrow (~44px collapsed)').toBeLessThan(120);
  expect(metrics.width, 'copilot must not be full-width').toBeGreaterThan(20);
  expect(metrics.right, 'copilot hugs the right edge of the shell').toBeGreaterThan(metrics.vw - 80);
  expect(metrics.left, 'copilot must not be centered as a bottom band').toBeGreaterThan(metrics.vw * 0.55);
  expect(metrics.height, 'copilot spans the middle row, not a shallow bottom strip').toBeGreaterThan(metrics.vh * 0.35);
  expect(metrics.shellCols, 'shell must define 3 columns including copilot track').toMatch(/44px|360px/);
});
