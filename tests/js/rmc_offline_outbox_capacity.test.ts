/**
 * Globalization 0.4 — offline outbox must never claim "saved" when it wasn't.
 *
 * MUST-FIRE contract (each test goes RED if the fix in
 * static/js/offline-queue-client.js is reverted):
 *   1. A quota failure on localStorage.setItem makes rmcOfflineEnqueue report
 *      FAILURE. Pre-fix writeOutboxLS swallowed the throw and enqueueAction
 *      returned undefined, so the UI toasted "Saved on this device".
 *   2. A quota failure raises a USER-VISIBLE alert in the DOM, not a console
 *      line.
 *   3. Hitting the row cap REFUSES the new row (never evicts an older unsynced
 *      one) and raises a user-visible alert. Pre-fix there was no cap at all.
 *   4. Nearing the cap emits back-pressure BEFORE the user loses work.
 *   5. A storage that accepts setItem and persists nothing (Safari private
 *      mode) is reported as failure, not success.
 *   6. The happy path still returns ok and raises no alarm.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

// Overridable so the must-fire proof can run the SAME assertions against a
// mechanically reverted copy of the client without touching the real file.
const SCRIPT_PATH =
  process.env.RMC_OFFLINE_QUEUE_CLIENT_PATH ||
  path.resolve(__dirname, "../../static/js/offline-queue-client.js");
const SCRIPT_SRC = fs.readFileSync(SCRIPT_PATH, "utf-8");

const LS_KEY = "rmc-offline-outbox-v1";
const ALERT_ID = "rmc-offline-storage-alert";

type EnqueueResult = {
  ok: boolean;
  reason?: string;
  storage?: string;
  queued?: number;
  detail?: string;
};

declare global {
  // eslint-disable-next-line no-var
  var rmcOfflineEnqueue: (payload: Record<string, unknown>) => EnqueueResult;
  // eslint-disable-next-line no-var
  var rmcOfflineOutboxLimits: {
    maxRows: number;
    maxChars: number;
    backPressureRatio: number;
    storageKey: string;
    alertElementId: string;
  };
}

function loadScript() {
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT_SRC)();
}

function enqueue(overrides: Record<string, unknown> = {}): EnqueueResult {
  return window.rmcOfflineEnqueue({
    action_type: "attendance",
    payload: { student_id: 11, classroom_id: 3, date: "2026-07-21", status: "present" },
    idempotency_key: "att-3-2026-07-21-11",
    ...overrides,
  }) as EnqueueResult;
}

function alertEl(): HTMLElement | null {
  return document.getElementById(ALERT_ID);
}

function alertText(): string {
  return alertEl()?.textContent ?? "";
}

/** Seed N already-queued rows straight into storage (fast; no O(n^2) loop). */
function seedOutbox(n: number) {
  const rows = [];
  for (let i = 0; i < n; i++) {
    rows.push({
      id: `seed-${i}`,
      payload: { action_type: "attendance", payload: { student_id: i } },
      ts: "2026-07-20T08:00:00.000Z",
      owner: "",
    });
  }
  window.localStorage.setItem(LS_KEY, JSON.stringify(rows));
  return rows;
}

/** Make writes to the outbox key throw QuotaExceededError; leave others alone. */
function breakOutboxWrites(reason: "quota" | "silent") {
  const real = Storage.prototype.setItem;
  return vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementation(function (this: Storage, key: string, value: string) {
      if (key === LS_KEY) {
        if (reason === "silent") return; // accepted, persists nothing
        const err: Error & { name: string; code?: number } = new Error(
          "The quota has been exceeded.",
        ) as never;
        err.name = "QuotaExceededError";
        err.code = 22;
        throw err;
      }
      return real.call(this, key, value);
    });
}

describe("offline-queue-client outbox capacity + honest persistence", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    delete (window as Record<string, unknown>).rmcOfflineEnqueue;
    delete (window as Record<string, unknown>).SMSOfflineDB;
    delete (window as Record<string, unknown>).RMCIamSnapshot;
    // No enqueue URL => flushIfOnline() is a no-op; we are unit-testing persistence.
    (window as Record<string, unknown>).SMS_OFFLINE_CONFIG = { currentUserId: "42" };
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("happy path: reports success, persists the row, raises no alarm", () => {
    loadScript();
    const res = enqueue();
    expect(res.ok).toBe(true);
    expect(res.storage).toBe("localstorage");
    expect(JSON.parse(window.localStorage.getItem(LS_KEY) as string)).toHaveLength(1);
    expect(alertEl()).toBeNull();
  });

  // MUST-FIRE #1 — pre-fix this returned undefined (falsy but not a report)
  // and the row was silently gone.
  it("reports FAILURE when the outbox write hits QuotaExceededError", () => {
    loadScript();
    breakOutboxWrites("quota");
    const res = enqueue();
    expect(res).toBeTruthy();
    expect(res.ok).toBe(false);
    expect(res.reason).toBe("quota_exceeded");
    // Nothing was persisted, and we did not pretend otherwise.
    expect(window.localStorage.getItem(LS_KEY)).toBeNull();
  });

  // MUST-FIRE #2 — the failure must reach the human, not just console.
  it("raises a user-visible alert (not a console line) on a failed write", () => {
    loadScript();
    breakOutboxWrites("quota");
    enqueue();
    const el = alertEl();
    expect(el).not.toBeNull();
    expect(el?.getAttribute("role")).toBe("alert");
    expect(el?.getAttribute("aria-live")).toBe("assertive");
    expect(el?.getAttribute("data-rmc-storage-alert-level")).toBe("error");
    expect(alertText()).toContain("NOT SAVED");
    expect(document.body.contains(el)).toBe(true);
  });

  // MUST-FIRE #5 — setItem returning is not proof the write landed.
  it("detects a storage that accepts the write but persists nothing", () => {
    loadScript();
    breakOutboxWrites("silent");
    const res = enqueue();
    expect(res.ok).toBe(false);
    expect(res.reason).toBe("write_not_persisted");
    expect(alertText()).toContain("NOT SAVED");
  });

  // MUST-FIRE #3 — cap exists, refuses the NEW row, keeps every OLD row.
  it("refuses the new row at the cap and keeps all older unsynced rows", () => {
    loadScript();
    const cap = window.rmcOfflineOutboxLimits.maxRows;
    expect(cap).toBeGreaterThan(0);
    seedOutbox(cap);

    const res = enqueue();
    expect(res.ok).toBe(false);
    expect(res.reason).toBe("outbox_full");
    expect(res.detail).toBe("row_cap");

    // REFUSE-NEW policy: not one older unsynced row was evicted.
    const stored = JSON.parse(window.localStorage.getItem(LS_KEY) as string);
    expect(stored).toHaveLength(cap);
    expect(stored[0].id).toBe("seed-0");
    expect(stored[cap - 1].id).toBe(`seed-${cap - 1}`);
  });

  it("cap refusal is user-visible, not a silent drop", () => {
    loadScript();
    seedOutbox(window.rmcOfflineOutboxLimits.maxRows);
    enqueue();
    const el = alertEl();
    expect(el).not.toBeNull();
    expect(el?.getAttribute("data-rmc-storage-alert-level")).toBe("error");
    expect(alertText()).toContain("NOT SAVED");
    expect(alertText()).toContain("full");
  });

  // MUST-FIRE #4 — warn BEFORE the user does more work they will lose.
  it("emits back-pressure before the cap is reached", () => {
    loadScript();
    const { maxRows, backPressureRatio } = window.rmcOfflineOutboxLimits;
    seedOutbox(Math.floor(maxRows * backPressureRatio) - 1);

    const res = enqueue();
    expect(res.ok).toBe(true); // still accepted...
    const el = alertEl();
    expect(el).not.toBeNull(); // ...but the user was warned already
    expect(el?.getAttribute("data-rmc-storage-alert-level")).toBe("warning");
    expect(alertText()).toContain("nearly full");
  });

  it("broadcasts a DOM event so producer toasts can suppress false success", () => {
    loadScript();
    const seen: Array<{ level: string; message: string }> = [];
    document.addEventListener("rmc-offline-storage-alert", (ev) => {
      seen.push((ev as CustomEvent).detail);
    });
    breakOutboxWrites("quota");
    enqueue();
    expect(seen).toHaveLength(1);
    expect(seen[0].level).toBe("error");
    expect(seen[0].message).toContain("NOT SAVED");
  });

  it("still returns a checkable result for guard-rejected payloads", () => {
    loadScript();
    expect(window.rmcOfflineEnqueue(null as never).ok).toBe(false);
    expect(window.rmcOfflineEnqueue({}).ok).toBe(false);
    expect(window.rmcOfflineEnqueue({}).reason).toBe("missing_action_type");
  });

  it("reports failure when the IndexedDB rail rejects", async () => {
    (window as Record<string, unknown>).SMSOfflineDB = {
      outboxEnqueue: () => Promise.reject(new Error("idb closed")),
    };
    loadScript();
    const res = enqueue() as EnqueueResult & { settled: Promise<EnqueueResult> };
    const settled = await res.settled;
    expect(settled.ok).toBe(false);
    expect(settled.reason).toBe("indexeddb_write_failed");
    expect(alertText()).toContain("NOT SAVED");
  });
});
