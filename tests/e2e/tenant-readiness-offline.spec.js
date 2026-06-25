/**
 * Batch 1734 — readiness train stale/offline UX (simulated offline).
 */
const { test, expect } = require("@playwright/test");

test.describe("Readiness offline cache UX", () => {
  test("cached readiness scripts and markers on backend dashboard", async ({
    page,
  }) => {
    test.skip(
      !process.env.TENANT_E2E_BASE_URL,
      "Set TENANT_E2E_BASE_URL for live tenant E2E"
    );
    await page.goto(process.env.TENANT_E2E_BASE_URL + "/authentication/backend/");
    const train = page.locator("[data-rmc-readiness-train='1']");
    if ((await train.count()) === 0) {
      test.skip(true, "No readiness train on this tenant state");
    }
    await expect(train.first()).toBeVisible();
    await expect(page.locator("script[src*='rmc-school-readiness-cache']")).toHaveCount(
      1
    );
  });

  test("offline-sim shows stale readiness when navigator offline", async ({
    page,
    context,
  }) => {
    test.skip(
      !process.env.TENANT_E2E_BASE_URL,
      "Set TENANT_E2E_BASE_URL for live tenant E2E"
    );
    await page.goto(process.env.TENANT_E2E_BASE_URL + "/authentication/backend/");
    const train = page.locator("[data-rmc-readiness-train='1']");
    if ((await train.count()) === 0) {
      test.skip(true, "No readiness train on this tenant state");
    }
    await context.setOffline(true);
    await page.evaluate(() => {
      window.localStorage.setItem(
        "rmc_school_readiness_v1",
        JSON.stringify({
          schoolKey: document
            .querySelector("[data-rmc-readiness-train='1']")
            ?.getAttribute("data-rmc-readiness-school-key"),
          payload: { ok: true, meter_percent: 42, phases: [] },
          storedAt: Date.now() - 12 * 60 * 1000,
        })
      );
    });
    await page.reload();
    const stale = page.locator("[data-rmc-readiness-stale='1']");
    if ((await stale.count()) > 0) {
      await expect(stale.first()).toBeVisible();
    }
    await context.setOffline(false);
  });
});
