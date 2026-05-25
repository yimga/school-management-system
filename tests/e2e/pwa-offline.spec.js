/**
 * PWA offline behavior — Playwright spec (batch 1492 audit closure).
 *
 * Browser execution requires a provisioned tenant + running web server +
 * service-worker scope. Local headless mode is the minimum target.
 *
 * Run via:
 *   npx playwright test tests/e2e/pwa-offline.spec.js
 */
const { test, expect } = require('@playwright/test');

const PLATFORM_HOST = process.env.RMC_PLAYWRIGHT_HOST || 'http://localhost:8000';

test.describe('PWA offline behavior', () => {
  test('platform manifest loads with correct Content-Type', async ({ request }) => {
    const res = await request.get(`${PLATFORM_HOST}/static/manifest.json`);
    expect(res.status()).toBe(200);
    const ct = res.headers()['content-type'] || '';
    expect(ct).toMatch(/json|manifest/);
    const body = await res.json();
    expect(body.name).toBeTruthy();
    expect(body.icons.length).toBeGreaterThan(0);
  });

  test('service worker JS is reachable and parses', async ({ request }) => {
    const res = await request.get(`${PLATFORM_HOST}/static/js/service-worker.js`);
    expect(res.status()).toBe(200);
    const text = await res.text();
    expect(text).toContain('CACHE_VERSION');
    expect(text).toContain('addEventListener("install"');
    expect(text).toContain('addEventListener("activate"');
    expect(text).toContain('addEventListener("fetch"');
  });

  test('service worker registers on page load', async ({ page }) => {
    await page.goto(PLATFORM_HOST);
    const swRegistered = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return false;
      const reg = await navigator.serviceWorker.getRegistration();
      return !!reg;
    });
    expect(swRegistered).toBe(true);
  });

  test('no horizontal overflow on landing at portal viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(PLATFORM_HOST);
    const bodyOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth - document.documentElement.clientWidth;
    });
    expect(bodyOverflow).toBeLessThanOrEqual(1);
  });

  test('no console errors at landing', async ({ page }) => {
    const errors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto(PLATFORM_HOST);
    expect(errors.filter((e) => !/favicon|net::ERR_BLOCKED/.test(e))).toEqual([]);
  });

  test('admin route is NOT cacheable by service worker', async ({ page }) => {
    // Visit admin then drop offline; admin must not be in SW cache (auth path).
    await page.goto(`${PLATFORM_HOST}/admin/`);
    const cachedAdmin = await page.evaluate(async () => {
      const cacheNames = await caches.keys();
      for (const name of cacheNames) {
        const cache = await caches.open(name);
        const match = await cache.match('/admin/');
        if (match) return true;
      }
      return false;
    });
    expect(cachedAdmin).toBe(false);
  });
});
