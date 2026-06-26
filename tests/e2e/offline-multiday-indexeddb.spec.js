// @ts-check
/**
 * Metric 8/25 — multi-day offline queue persistence in real Chromium IndexedDB.
 * Mirrors the 7-day server replay in test_offline_multiday_replay_simulation.py
 * at the browser producer layer (attendance + grading rows).
 *
 * Serverless: injects Dexie + offline-db + queue-client on about:blank so CI
 * does not depend on Django webServer boot time (migrate+seed can exceed 2 min).
 */
const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const DEXIE_SRC = fs.readFileSync(
  path.resolve(__dirname, "..", "..", "static", "js", "vendor", "dexie.min.js"),
  "utf8"
);
const OFFLINE_DB_SRC = fs.readFileSync(
  path.resolve(__dirname, "..", "..", "static", "js", "offline-db.js"),
  "utf8"
);
const QUEUE_CLIENT_SRC = fs.readFileSync(
  path.resolve(__dirname, "..", "..", "static", "js", "offline-queue-client.js"),
  "utf8"
);

async function mountOfflineStack(page, { clearOutbox = false } = {}) {
  const bootUrl = "/offline-indexeddb-boot.html";
  if (clearOutbox) {
    await page.goto(bootUrl, { waitUntil: "domcontentloaded" });
    await page.evaluate(() => {
      localStorage.removeItem("rmc-offline-outbox-v1");
    });
  } else if (!page.url().includes("offline-indexeddb-boot")) {
    await page.goto(bootUrl, { waitUntil: "domcontentloaded" });
  }
  await page.evaluate(() => {
    window.global = window;
    window.SMS_OFFLINE_CONFIG = {
      currentUserId: "teacher-e2e-1",
      offlineEnqueueUrl: "/portal/api/offline/enqueue/",
      offlineProcessUrl: "/portal/api/offline/process/",
    };
  });
  await page.addScriptTag({ content: DEXIE_SRC });
  await page.addScriptTag({ content: OFFLINE_DB_SRC });
  await page.addScriptTag({ content: QUEUE_CLIENT_SRC });
  await page.waitForFunction(
    () =>
      typeof window.rmcOfflineEnqueue === "function" &&
      window.SMSOfflineDB &&
      typeof window.SMSOfflineDB.outboxPending === "function"
  );
}

test.describe("SODP multi-day IndexedDB queue", () => {
  test("seven attendance days + grading persist in Dexie outbox across reload", async ({
    page,
  }) => {
    await mountOfflineStack(page, { clearOutbox: true });

    const summary = await page.evaluate(async () => {
      const classroomId = 101;
      for (let day = 1; day <= 7; day += 1) {
        const isoDate = `2026-06-${String(day).padStart(2, "0")}`;
        window.rmcOfflineEnqueue({
          action_type: "attendance.mark",
          classroom_id: classroomId,
          date: isoDate,
          status: "present",
          idempotency_key: `att-e2e-${isoDate}`,
        });
      }
      window.rmcOfflineEnqueue({
        action_type: "grade.submit",
        evaluation_id: 9001,
        seq1_score: 14,
        academic_year_id: 1,
        term_id: 1,
        idempotency_key: "grade-e2e-day-7",
      });
      await new Promise((r) => setTimeout(r, 250));
      const pending = await window.SMSOfflineDB.outboxPending();
      return {
        count: pending.length,
        actionTypes: pending.map((row) => row.action_type || ""),
      };
    });

    expect(summary.count).toBe(8);
    expect(summary.actionTypes.filter((t) => t === "attendance.mark").length).toBe(
      7
    );
    expect(summary.actionTypes).toContain("grade.submit");

    await page.reload({ waitUntil: "domcontentloaded" });
    await mountOfflineStack(page, { clearOutbox: false });

    const afterReload = await page.evaluate(async () => {
      const pending = await window.SMSOfflineDB.outboxPending();
      return pending.length;
    });
    expect(afterReload).toBe(8);
  });
});
