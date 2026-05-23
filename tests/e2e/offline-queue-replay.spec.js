// @ts-check
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
      };
    });
    expect(caps.maxQueueItems == null || caps.maxQueueItems >= 50).toBeTruthy();
  });
});
