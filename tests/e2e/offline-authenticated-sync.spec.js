// @ts-check
/**
 * Metric 8/25 — authenticated teacher offline enqueue → server replay (browser).
 *
 * Requires a running tenant E2E server (seed can take ~2 min on first boot):
 *   VISUAL_QA_PORT=8013 node scripts/playwright_tenant_web_server.mjs
 *   RMC_E2E_EXTERNAL_SERVER=1 npm run test:e2e:offline-authenticated-sync
 *
 * Server-side proof lives in apps/portal/tests/test_offline_authenticated_api_replay.py
 */
const { test, expect } = require("@playwright/test");

function loadLoginTenant(baseUrl) {
  if (baseUrl) {
    process.env.TENANT_E2E_BASE_URL = baseUrl.replace(/\/$/, "");
    process.env.PLAYWRIGHT_TENANT_BASE_URL = process.env.TENANT_E2E_BASE_URL;
  }
  delete require.cache[require.resolve("./helpers/tenant-login")];
  return require("./helpers/tenant-login");
}

test.describe("Authenticated offline → server sync", () => {
  test.beforeEach(() => {
    // CI uses playwright.config.js webServer; local dev can pre-warm or set RMC_E2E_EXTERNAL_SERVER=1.
    if (process.env.CI === "1") {
      return;
    }
    test.skip(
      process.env.RMC_E2E_EXTERNAL_SERVER !== "1",
      "Set RMC_E2E_EXTERNAL_SERVER=1 with tenant E2E server on VISUAL_QA_PORT (8013)"
    );
  });

  test("teacher queues offline then flush syncs on server", async ({
    page,
    context,
  }, testInfo) => {
    const tenantBase = String(testInfo.project.use.baseURL || "").replace(/\/$/, "");
    const { loginTenant } = loadLoginTenant(tenantBase);

    await loginTenant(page, {
      username: process.env.E2E_TENANT_TEACHER_USER || "demo.teacher",
    });

    await page.goto(`${tenantBase}/portal/`, {
      waitUntil: "domcontentloaded",
      timeout: 120000,
    });
    await page.waitForFunction(
      () =>
        typeof window.rmcOfflineEnqueue === "function" &&
        !!(window.SMS_OFFLINE_CONFIG || {}).offlineEnqueueUrl
    );

    const idemKey = `pw-ticket-${Date.now()}`;

    await context.setOffline(true);
    await page.evaluate((key) => {
      window.rmcOfflineEnqueue({
        action_type: "support.ticket",
        subject: "E2E offline authenticated sync",
        message: "Playwright proof row — safe to close as duplicate.",
        idempotency_key: key,
      });
    }, idemKey);

    const localPending = await page.evaluate(async () => {
      if (window.SMSOfflineDB && window.SMSOfflineDB.outboxPending) {
        const rows = await window.SMSOfflineDB.outboxPending();
        return rows.length;
      }
      try {
        const raw = localStorage.getItem("rmc-offline-outbox-v1");
        return raw ? JSON.parse(raw).length : 0;
      } catch (_e) {
        return 0;
      }
    });
    expect(localPending).toBeGreaterThan(0);

    await context.setOffline(false);
    await page.waitForTimeout(500);

    const processSummary = await page.evaluate(async () => {
      const cfg = window.SMS_OFFLINE_CONFIG || {};
      const enqueueUrl = cfg.offlineEnqueueUrl || cfg.offline_enqueue_url;
      const processUrl =
        cfg.offlineProcessUrl ||
        cfg.offline_process_url ||
        (enqueueUrl ? enqueueUrl.replace(/enqueue\/?$/, "process/") : "");
      if (typeof window.rmcOfflineFlushNow === "function") {
        window.rmcOfflineFlushNow();
      }
      await new Promise((r) => setTimeout(r, 1500));
      if (!processUrl) {
        return { ok: false, error: "missing_process_url" };
      }
      const csrf =
        document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
        document.querySelector('input[name="csrfmiddlewaretoken"]')?.value ||
        "";
      const res = await fetch(processUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: "{}",
      });
      return res.json();
    });

    expect(processSummary.ok).toBeTruthy();
    expect(processSummary.synced ?? 0).toBeGreaterThan(0);

    const serverPending = await page.evaluate(async (key) => {
      const cfg = window.SMS_OFFLINE_CONFIG || {};
      const enqueueUrl = cfg.offlineEnqueueUrl || cfg.offline_enqueue_url;
      const processUrl =
        cfg.offlineProcessUrl ||
        cfg.offline_process_url ||
        (enqueueUrl ? enqueueUrl.replace(/enqueue\/?$/, "process/") : "");
      if (typeof window.rmcOfflineFlushNow === "function") {
        window.rmcOfflineFlushNow();
      }
      await new Promise((r) => setTimeout(r, 800));
      if (window.SMSOfflineDB && window.SMSOfflineDB.outboxPending) {
        const rows = await window.SMSOfflineDB.outboxPending();
        return rows.filter(
          (row) =>
            (row.idempotency_key || row.payload?.idempotency_key || "") === key
        ).length;
      }
      return 0;
    }, idemKey);
    expect(serverPending).toBe(0);
  });
});
