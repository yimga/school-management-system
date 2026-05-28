/**
 * v4.00.7 — Vitest unit coverage for the attendance WAL progressive enhancement.
 *
 * Runs in jsdom. Verifies the script:
 *   (1) is a no-op when window.rmcWAL is missing
 *   (2) intercepts the save button click when rmcWAL is present and ships a
 *       single envelope containing one row per .status-select
 *   (3) does NOT intercept on the teacher form (data-attendance-scope="teacher")
 *   (4) falls back to form.submit() when rmcWAL.append rejects
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT_PATH = path.resolve(
  __dirname,
  "../../static/js/_pages/rmc-attendance-wal-enhance.js",
);
const SCRIPT_SRC = fs.readFileSync(SCRIPT_PATH, "utf-8");

function loadScript() {
  // The script uses an IIFE guarded by window.__rmcAttendanceWALBound;
  // tests reset that flag between runs so each test boots fresh.
  delete window.__rmcAttendanceWALBound;
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT_SRC)();
}

function buildStudentForm() {
  document.body.innerHTML = `
    <form method="post">
      <input name="date" value="2026-05-28">
      <input name="classroom" value="cl-1">
      <div data-attendance-scope="student">
        <select name="status_11" class="status-select"><option value="present">P</option></select>
        <select name="status_22" class="status-select"><option value="present">P</option></select>
        <select name="status_33" class="status-select"><option value="absent" selected>A</option></select>
      </div>
      <button type="button" id="save-all-present">Save all present</button>
    </form>`;
  return document.querySelector("form");
}

function buildTeacherForm() {
  document.body.innerHTML = `
    <form method="post">
      <input name="date" value="2026-05-28">
      <div data-attendance-scope="teacher">
        <select name="status_99" class="status-select"><option value="present">P</option></select>
      </div>
      <button type="button" id="save-all-present">Save all present</button>
    </form>`;
  return document.querySelector("form");
}

describe("rmc-attendance-wal-enhance", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    delete window.rmcWAL;
    delete window.__rmcAttendanceWALBound;
    window.__RMC_PAGE_DATA__ = {
      "portal__roll_call_student-1": { var_attendance_present: "present" },
    };
  });

  it("no-ops when window.rmcWAL is missing", () => {
    const form = buildStudentForm();
    const submitSpy = vi.spyOn(form, "submit").mockImplementation(() => {});
    loadScript();
    document.getElementById("save-all-present").click();
    // Without rmcWAL, the script binds nothing — no intercept, no call.
    expect(submitSpy).not.toHaveBeenCalled();
  });

  it("ships one envelope with one row per .status-select on student form", async () => {
    const form = buildStudentForm();
    const append = vi.fn().mockResolvedValue("txn-abcdef");
    window.rmcWAL = { append, flush: vi.fn(), pending: vi.fn(), onAck: vi.fn() };
    loadScript();
    document.getElementById("save-all-present").click();
    expect(append).toHaveBeenCalledTimes(1);
    const [domain, actions] = append.mock.calls[0];
    expect(domain).toBe("attendance");
    expect(actions).toHaveLength(3);
    const ids = actions.map((a) => a.student_id).sort();
    expect(ids).toEqual(["11", "22", "33"]);
    actions.forEach((a) => {
      expect(a.session_id).toBe("cl-1::2026-05-28");
      expect(typeof a.marked_at).toBe("string");
    });
    expect(actions.every((a) => a.status === "present")).toBe(true);
  });

  it("ships a teacher_attendance envelope with uppercased status on teacher form", () => {
    const form = buildTeacherForm();
    const append = vi.fn().mockResolvedValue("txn-teach");
    window.rmcWAL = { append, flush: vi.fn(), pending: vi.fn(), onAck: vi.fn() };
    loadScript();
    document.getElementById("save-all-present").click();
    expect(append).toHaveBeenCalledTimes(1);
    const [domain, actions] = append.mock.calls[0];
    expect(domain).toBe("teacher_attendance");
    expect(actions).toHaveLength(1);
    expect(actions[0].teacher_id).toBe("99");
    expect(actions[0].date).toBe("2026-05-28");
    expect(actions[0].status).toBe("PRESENT");
    expect(actions[0]).not.toHaveProperty("session_id");
    expect(actions[0]).not.toHaveProperty("classroom_id");
  });

  it("does NOT intercept when neither student nor teacher gate is present", () => {
    document.body.innerHTML = `
      <form method="post">
        <input name="date" value="2026-05-28">
        <select name="status_55" class="status-select"><option value="present">P</option></select>
        <button type="button" id="save-all-present">Save all present</button>
      </form>`;
    const append = vi.fn();
    window.rmcWAL = { append, flush: vi.fn(), pending: vi.fn(), onAck: vi.fn() };
    loadScript();
    document.getElementById("save-all-present").click();
    expect(append).not.toHaveBeenCalled();
  });

  it("falls back to form.submit() when rmcWAL.append rejects", async () => {
    const form = buildStudentForm();
    const submitSpy = vi.spyOn(form, "submit").mockImplementation(() => {});
    const append = vi.fn().mockRejectedValue(new Error("ws closed"));
    window.rmcWAL = { append, flush: vi.fn(), pending: vi.fn(), onAck: vi.fn() };
    loadScript();
    document.getElementById("save-all-present").click();
    // Let the promise rejection resolve.
    await new Promise((r) => setTimeout(r, 0));
    expect(submitSpy).toHaveBeenCalled();
  });
});
