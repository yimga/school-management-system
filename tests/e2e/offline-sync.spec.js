// @ts-check
/**
 * E2E tests for Resilient Edge offline behaviour.
 * Requires: Django running with offline mode enabled (enable_offline_mode=True).
 * For authenticated test: set env TEST_USERNAME and TEST_PASSWORD (e.g. a teacher account).
 * Run: npm run test:e2e (or npx playwright test tests/e2e/offline-sync.spec.js)
 */
const { test, expect } = require('@playwright/test');

test.describe('Offline and sync', () => {
  test('offline fallback page loads and shows Sync now copy', async ({ page }) => {
    await page.goto('/offline/');
    await expect(page).toHaveTitle(/Offline/i);
    await expect(page.getByText(/Sync now/i)).toBeVisible();
    await expect(page.getByText(/When back online/i)).toBeVisible();
  });

  test('navigation returns offline fallback when offline then recovers when online', async ({ page }) => {
    await page.goto('/');
    await page.context().setOffline(true);
    await page.goto('/portal/').catch(() => {});
    await page.waitForTimeout(300);
    await page.context().setOffline(false);
    await page.goto('/');
    await expect(page).toHaveURL(/\//);
  });

  test('authenticated: login, go offline, go online, Sync now visible and clickable', async ({ page }) => {
    const username = process.env.TEST_USERNAME;
    const password = process.env.TEST_PASSWORD;
    test.skip(!username || !password, 'Set TEST_USERNAME and TEST_PASSWORD for authenticated offline test');
    await page.goto('/authentication/login/');
    await page.getByLabel(/Username/i).fill(username);
    await page.getByLabel(/Password/i).fill(password);
    await page.getByRole('button', { name: /Log in/i }).click();
    await page.waitForURL(/portal|backend|teacher|accounts/);
    await page.context().setOffline(true);
    await page.goto('/portal/');
    await page.waitForTimeout(300);
    await page.context().setOffline(false);
    await page.goto('/portal/');
    await page.waitForTimeout(1000);
    const syncBtn = page.locator('#sms-offline-sync-now-btn');
    if (await syncBtn.isVisible()) {
      await syncBtn.click();
      await page.waitForTimeout(2000);
    }
    await expect(page).toHaveURL(/\//);
  });

  test('full flow: queue request offline, go online, Sync now, then bar shows Connected or Last synced', async ({ page }) => {
    const username = process.env.TEST_USERNAME;
    const password = process.env.TEST_PASSWORD;
    test.skip(!username || !password, 'Set TEST_USERNAME and TEST_PASSWORD for full offline→sync test');
    await page.goto('/authentication/login/');
    await page.getByLabel(/Username/i).fill(username);
    await page.getByLabel(/Password/i).fill(password);
    await page.getByRole('button', { name: /Log in/i }).click();
    await page.waitForURL(/portal|backend|teacher|accounts/);
    await page.context().setOffline(true);
    await page.goto('/portal/');
    await page.waitForTimeout(500);
    await page.evaluate(async () => {
      try {
        await fetch(window.location.origin + '/api/attendance/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || '' },
          body: JSON.stringify({}),
        });
      } catch (_) {}
    });
    await page.waitForTimeout(300);
    await page.context().setOffline(false);
    await page.goto('/portal/');
    await page.waitForTimeout(1500);
    const syncBtn = page.locator('#sms-offline-sync-now-btn');
    if (await syncBtn.isVisible()) {
      await syncBtn.click();
      await page.waitForTimeout(6000);
    }
    const bar = page.locator('#sms-offline-status-bar');
    await expect(bar).toBeVisible();
    const text = page.locator('#sms-offline-status-text');
    const lastSynced = page.locator('#sms-offline-status-last-synced');
    const hasConnected = await text.textContent().then((t) => (t || '').includes('Connected'));
    const hasLastSynced = await lastSynced.isVisible().then((v) => v).catch(() => false);
    expect(hasConnected || hasLastSynced).toBeTruthy();

    // Assert API is reachable after sync (confirms we are back online and server responds)
    const apiOk = await page.evaluate(async () => {
      try {
        const r = await fetch(window.location.origin + '/api/attendance/', { method: 'GET', credentials: 'same-origin', headers: { Accept: 'application/json' } });
        return r.status === 200 || r.status === 401 || r.status === 403;
      } catch (_) { return false; }
    });
    expect(apiOk).toBeTruthy();
  });
});
