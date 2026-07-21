/**
 * Offline capture forms must never claim work was saved when it was not.
 *
 * THE DEFECT THIS GUARDS
 * ----------------------
 * Every offline form in `rmc-offline-portal-forms.js` used to call
 * `window.rmcOfflineEnqueue(...)` and then unconditionally toast
 * "Saved on this device" / "Queued N attendance row(s)". The enqueue could not
 * report failure (it returned `undefined`) and its localStorage write swallowed
 * `QuotaExceededError`. So when a teacher's device outbox was full, the register
 * was discarded and the teacher was told it was safe -- the worst failure mode
 * for a platform whose users are offline for days at a time.
 *
 * These tests drive the real script in jsdom with an enqueue that reports
 * failure, and assert the user is told the truth. They are must-fire: restore
 * the unconditional toast and every one of them goes red.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT_PATH = path.resolve(
  __dirname,
  "../../static/js/rmc-offline-portal-forms.js",
);
const SCRIPT_SRC = fs.readFileSync(SCRIPT_PATH, "utf-8");

/** Messages the script shows. Bootstrap is absent in jsdom, so it falls back to alert(). */
let shown: string[] = [];

function boot() {
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT_SRC)();
  document.dispatchEvent(new Event("DOMContentLoaded"));
}

function setOffline() {
  Object.defineProperty(window.navigator, "onLine", {
    value: false,
    configurable: true,
  });
}

function enqueueReturning(result: unknown) {
  const spy = vi.fn(() => result);
  (window as any).rmcOfflineEnqueue = spy;
  return spy;
}

function claimsSuccess(): boolean {
  return shown.some(
    (m) =>
      /saved on this device/i.test(m) ||
      /^queued \d+ /i.test(m) ||
      /queued for sync/i.test(m) ||
      /will sync when you reconnect/i.test(m),
  );
}

function warnsNotSaved(): boolean {
  return shown.some((m) => /NOT SAVED|PARTIALLY SAVED/.test(m));
}

beforeEach(() => {
  shown = [];
  vi.spyOn(window, "alert").mockImplementation((msg?: unknown) => {
    shown.push(String(msg));
  });
  (window as any).SMS_OFFLINE_CONFIG = {
    formQueueEnabled: true,
    offlineEnqueueUrl: "/offline/enqueue/",
  };
  setOffline();
  document.body.innerHTML = "";
});

describe("offline forms report the real enqueue outcome", () => {
  it("does NOT claim a note was saved when the outbox write failed", () => {
    enqueueReturning({ ok: false, reason: "quota_exceeded" });
    document.body.innerHTML = `
      <form data-rmc-offline-form="notes_report" data-rmc-offline-note-url="/x/">
        <textarea name="body">Safeguarding note</textarea>
      </form>`;
    boot();
    document
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    expect(claimsSuccess()).toBe(false);
    expect(warnsNotSaved()).toBe(true);
  });

  it("names the cause when the device outbox is full", () => {
    enqueueReturning({ ok: false, reason: "outbox_full" });
    document.body.innerHTML = `
      <form data-rmc-offline-form="homework_submission">
        <input name="homework_id" value="7">
        <input name="student_id" value="42">
        <textarea name="submission_text">My essay</textarea>
      </form>`;
    boot();
    document
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    expect(claimsSuccess()).toBe(false);
    expect(shown.join(" ")).toMatch(/full/i);
  });

  it("still confirms success when the enqueue really succeeded", () => {
    enqueueReturning({ ok: true });
    document.body.innerHTML = `
      <form data-rmc-offline-form="homework_submission">
        <input name="homework_id" value="7">
        <input name="student_id" value="42">
        <textarea name="submission_text">My essay</textarea>
      </form>`;
    boot();
    document
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    expect(claimsSuccess()).toBe(true);
    expect(warnsNotSaved()).toBe(false);
  });

  it("treats a legacy undefined return as NOT saved, never as success", () => {
    // A stale cached build of offline-queue-client.js returns undefined. The safe
    // direction for "did the write land?" is to assume it did not.
    enqueueReturning(undefined);
    document.body.innerHTML = `
      <form data-rmc-offline-form="notes_report" data-rmc-offline-note-url="/x/">
        <textarea name="body">Note</textarea>
      </form>`;
    boot();
    document
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    expect(claimsSuccess()).toBe(false);
  });

  it("reports a whole failed attendance register as NOT SAVED, not 'Queued 3'", () => {
    enqueueReturning({ ok: false, reason: "quota_exceeded" });
    document.body.innerHTML = `
      <form data-rmc-offline-form="attendance">
        <input name="date" value="2026-07-21">
        <input name="classroom" value="5">
        <select name="status_11"><option value="present" selected>P</option></select>
        <select name="status_22"><option value="absent" selected>A</option></select>
        <select name="status_33"><option value="present" selected>P</option></select>
      </form>`;
    boot();
    document
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    expect(claimsSuccess()).toBe(false);
    expect(shown.join(" ")).toMatch(/NOT SAVED/);
  });

  it("distinguishes a PARTIALLY saved register from a fully saved one", () => {
    let call = 0;
    (window as any).rmcOfflineEnqueue = vi.fn(() => {
      call += 1;
      return call === 2 ? { ok: false, reason: "outbox_full" } : { ok: true };
    });
    document.body.innerHTML = `
      <form data-rmc-offline-form="attendance">
        <input name="date" value="2026-07-21">
        <input name="classroom" value="5">
        <select name="status_11"><option value="present" selected>P</option></select>
        <select name="status_22"><option value="absent" selected>A</option></select>
        <select name="status_33"><option value="present" selected>P</option></select>
      </form>`;
    boot();
    document
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

    const joined = shown.join(" ");
    expect(joined).toMatch(/PARTIALLY SAVED/);
    expect(joined).toMatch(/2 of 3/);
  });
});
