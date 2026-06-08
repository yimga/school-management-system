// @ts-check
/**
 * Offline SVG parity via static preview (no manager login required).
 * Serves repo root on :8765 — preview loads /static/js/* and globe bundle.
 *
 *   npx playwright test world-globe-preview-offline --project=globe-preview-chromium
 */
const { test, expect } = require('@playwright/test');

const PREVIEW_PATH = '/artifacts/global-footprint-section-preview.html';

async function readGlobeMetrics(page) {
  return page.evaluate(() => {
    const stage = document.getElementById('rmc-world-globe-stage');
    const svg = stage ? stage.querySelector('.lx-world__svg-fallback') : null;
    const freshness = document.getElementById('rmc-world-globe-freshness');
    return {
      landCount: svg ? svg.querySelectorAll('.lx-world__svg-land').length : 0,
      dotCount: svg ? svg.querySelectorAll('.lx-world__dot-group').length : 0,
      svgHidden: svg ? svg.hidden : true,
      mode: stage ? stage.getAttribute('data-rmc-globe-mode') : null,
      freshness: freshness ? freshness.textContent.trim() : '',
    };
  });
}

test.describe('world globe preview offline parity', () => {
  test('offline toggle keeps SVG lands, dots, and bridge freshness', async ({ page }) => {
    test.setTimeout(120000);
    await page.goto(PREVIEW_PATH, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.locator('.lx-world').first().waitFor({ state: 'visible', timeout: 30000 });

    await page.locator('#mode-offline').click();
    await expect
      .poll(async () => (await readGlobeMetrics(page)).freshness, { timeout: 15000 })
      .toContain('Offline');

    const offline = await readGlobeMetrics(page);
    expect(offline.landCount).toBeGreaterThanOrEqual(4);
    expect(offline.dotCount).toBeGreaterThanOrEqual(4);
    expect(offline.svgHidden).toBe(false);
    expect(offline.mode).toBe('svg-offline');

    // Legend hover still works offline (bridge wired once).
    const row = page.locator('[data-rmc-region="West Africa"].lx-world__legend-row').first();
    await row.hover();
    const highlighted = await page.evaluate(() => {
      const land = document.querySelector('.lx-world__svg-land[data-rmc-region="West Africa"]');
      return land ? land.style.opacity : '';
    });
    expect(highlighted).toBe('1');
  });

  test('loader offline event preserves SVG markup', async ({ page, context }) => {
    test.setTimeout(120000);
    await page.goto(PREVIEW_PATH, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.locator('#mode-online').click({ trial: true }).catch(() => {});
    await page.waitForTimeout(1500);

    await context.setOffline(true);
    await page.evaluate(() => window.dispatchEvent(new Event('offline')));
    await page.waitForTimeout(1500);

    const metrics = await readGlobeMetrics(page);
    expect(metrics.landCount).toBeGreaterThanOrEqual(4);
    expect(metrics.dotCount).toBeGreaterThanOrEqual(4);
    expect(metrics.svgHidden).toBe(false);
  });
});
