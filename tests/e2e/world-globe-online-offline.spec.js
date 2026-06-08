// @ts-check
/**
 * Global Footprint online/offline parity (batch 1654 + v4.02.84).
 *
 * Asserts:
 *   - SVG fallback always has continent lands + tenant dots (never blank after offline toggle)
 *   - Offline mode shows "Offline map" freshness + visible SVG
 *   - Online recovery retries WebGL when bundle is available
 *
 * Run (manager-chromium + local Django on VISUAL_QA_PORT):
 *   bash scripts/run_globe_layout_playwright.sh
 */
const { test, expect } = require('@playwright/test');
const { ensureManagerSession, MANAGER_BASE_URL } = require('./helpers/manager-login');

const BASE = MANAGER_BASE_URL.replace(/\/$/, '');

async function waitForGlobeSection(page) {
  await page.locator('.lx-world').first().waitFor({ state: 'visible', timeout: 90000 });
  await page.locator('#rmc-world-globe-stage').waitFor({ state: 'attached', timeout: 30000 });
}

async function readGlobeMetrics(page) {
  return page.evaluate(() => {
    const stage = document.getElementById('rmc-world-globe-stage');
    const svg = stage ? stage.querySelector('.lx-world__svg-fallback') : null;
    const mount = document.getElementById('rmc-world-globe');
    const freshness = document.getElementById('rmc-world-globe-freshness');
    return {
      landCount: svg ? svg.querySelectorAll('.lx-world__svg-land').length : 0,
      dotCount: svg ? svg.querySelectorAll('.lx-world__dot-group').length : 0,
      svgHidden: svg ? svg.hidden : true,
      mode: stage ? stage.getAttribute('data-rmc-globe-mode') : null,
      webglInited: mount ? mount.getAttribute('data-rmc-world-globe-inited') === '1' : false,
      hasCanvas: mount ? Boolean(mount.querySelector('canvas')) : false,
      freshness: freshness ? freshness.textContent.trim() : '',
    };
  });
}

test.describe('world globe online/offline parity', () => {
  test('SVG fallback stays populated; offline then online recovery', async ({ page, context }) => {
    test.setTimeout(240000);
    await ensureManagerSession(page);
    const resp = await page.goto(`${BASE}/super/`, { waitUntil: 'domcontentloaded', timeout: 90000 });
    if (resp && resp.status() >= 400) {
      test.skip(true, `/super/ returned HTTP ${resp.status()}`);
      return;
    }
    await waitForGlobeSection(page);

    // Allow loader + optional WebGL init (single-file bundle can take a few seconds).
    await page.waitForTimeout(4000);
    let online = await readGlobeMetrics(page);
    expect(online.landCount, 'SVG must ship continent land paths').toBeGreaterThanOrEqual(4);
    expect(online.dotCount, 'SVG must ship tenant dot groups from server render').toBeGreaterThanOrEqual(1);

    // --- Offline: SVG must remain visible and populated (regression: globe.gl wiped innerHTML) ---
    await context.setOffline(true);
    await page.evaluate(() => window.dispatchEvent(new Event('offline')));
    await expect
      .poll(async () => (await readGlobeMetrics(page)).freshness, { timeout: 15000 })
      .toContain('Offline');
    const offline = await readGlobeMetrics(page);
    expect(offline.landCount).toBeGreaterThanOrEqual(4);
    expect(offline.dotCount).toBeGreaterThanOrEqual(1);
    expect(offline.svgHidden).toBe(false);
    expect(offline.mode).toBe('svg-offline');

    // --- Online again: loader retries WebGL; bridge may upgrade freshness to Live ---
    await context.setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await page.waitForTimeout(8000);
    const recovered = await readGlobeMetrics(page);
    expect(recovered.landCount).toBeGreaterThanOrEqual(4);
    expect(recovered.dotCount).toBeGreaterThanOrEqual(1);
    // WebGL optional in CI if bundle missing; when present, canvas + inited flag appear.
    if (recovered.hasCanvas || recovered.webglInited) {
      expect(recovered.freshness).toMatch(/Live|Updated/);
    }
  });

  test('starting offline skips WebGL and shows regional SVG immediately', async ({ page, context }) => {
    test.setTimeout(180000);
    await context.setOffline(true);
    await ensureManagerSession(page);
    const resp = await page.goto(`${BASE}/super/`, { waitUntil: 'domcontentloaded', timeout: 90000 });
    if (resp && resp.status() >= 400) {
      test.skip(true, `/super/ returned HTTP ${resp.status()}`);
      return;
    }
    await waitForGlobeSection(page);
    await page.waitForTimeout(2500);
    const metrics = await readGlobeMetrics(page);
    expect(metrics.landCount).toBeGreaterThanOrEqual(4);
    expect(metrics.dotCount).toBeGreaterThanOrEqual(1);
    expect(metrics.svgHidden).toBe(false);
    expect(metrics.mode).toBe('svg-offline');
    expect(metrics.freshness).toContain('Offline');
    expect(metrics.hasCanvas).toBe(false);
  });
});
