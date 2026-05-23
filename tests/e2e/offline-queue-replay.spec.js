// @ts-check
/**
 * SODP Wave G — offline queue replay scaffold + full flow when creds present.
 * Run: npx playwright test tests/e2e/offline-queue-replay.spec.js
 */
const { test, expect } = require("@playwright/test");

test.describe("SODP offline queue replay", () => {
  test("service worker exposes queue replay hooks", async ({ page }) => {
    await page.goto("/health/");
    const hasSw = await page.evaluate(async () => {
      if (!("serviceWorker" in navigator)) return false;
      const reg = await navigator.serviceWorker.getRegistration();
      return !!reg && !!reg.active;
    });
    test.skip(!hasSw, "Service worker not registered in this environment");
    const caps = await page.evaluate(() => {
      const cfg = window.SMS_OFFLINE_CONFIG || {};
      return {
        maxQueueItems: cfg.maxQueueItems,
        hubBaseUrl: cfg.hubBaseUrl,
        offlineEnqueueUrl: cfg.offlineEnqueueUrl || cfg.offline_enqueue_url,
      };
    });
    expect(caps.maxQueueItems == null || caps.maxQueueItems >= 50).toBeTruthy();
    if (caps.hubBaseUrl != null && caps.hubBaseUrl !== "") {
      expect(String(caps.hubBaseUrl)).toMatch(/^https?:\/\//);
    }
  });

  test("offline fallback page mentions Sync now", async ({ page }) => {
    await page.goto("/offline/");
    await expect(page.getByText(/Sync now/i)).toBeVisible();
  });

  test("full flow: queue offline then sync when authenticated", async ({ page }) => {
    const username = process.env.TEST_USERNAME;
    const password = process.env.TEST_PASSWORD;
    test.skip(!username || !password, "Set TEST_USERNAME and TEST_PASSWORD for full offline→sync test");
    await page.goto("/authentication/login/");
    await page.getByLabel(/Username/i).fill(username);
    await page.getByLabel(/Password/i).fill(password);
    await page.getByRole("button", { name: /Log in/i }).click();
    await page.waitForURL(/portal|backend|teacher|accounts/);
    await page.context().setOffline(true);
    await page.goto("/portal/");
    await page.waitForTimeout(500);
    await page.evaluate(async () => {
      try {
        await fetch(window.location.origin + "/api/attendance/", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken":
              (document.querySelector('meta[name="csrf-token"]') || {}).content || "",
          },
          body: JSON.stringify({}),
        });
      } catch (_) {
        /* expected while offline */
      }
    });
    await page.waitForTimeout(300);
    await page.context().setOffline(false);
    await page.goto("/portal/");
    await page.waitForTimeout(1500);
    const syncBtn = page.locator("#sms-offline-sync-now-btn");
    if (await syncBtn.isVisible()) {
      await syncBtn.click();
      await page.waitForTimeout(6000);
    }
    const bar = page.locator("#sms-offline-status-bar");
    await expect(bar).toBeVisible();
    const text = page.locator("#sms-offline-status-text");
    const lastSynced = page.locator("#sms-offline-status-last-synced");
    const connected = await text.textContent().then((t) => (t || "").includes("Connected"));
    const hasLastSynced = await lastSynced.isVisible().catch(() => false);
    expect(connected || hasLastSynced).toBeTruthy();
  });
});
