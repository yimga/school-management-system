/**
 * v4.00.10 — Vitest coverage for the bulk gradebook WAL progressive enhancement.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT_PATH = path.resolve(
  __dirname,
  "../../static/js/_pages/rmc-gradebook-wal-enhance.js",
);
const SCRIPT_SRC = fs.readFileSync(SCRIPT_PATH, "utf-8");

function loadScript() {
  delete (window as any).__rmcGradebookWALBound;
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT_SRC)();
}

function buildForm({ withYear = true, withTerm = true } = {}) {
  document.body.innerHTML = `
    <form id="marks-entry-form" data-rmc-offline-form="grading"
          ${withYear ? 'data-rmc-year-id="11"' : ""}
          ${withTerm ? 'data-rmc-term-id="22"' : ""}>
      <input type="hidden" name="subject_assignment_id" value="33">
      <table>
        <tbody>
          <tr>
            <td><input class="mark-cell" name="seq1_101" value="80"></td>
            <td><input class="mark-cell" name="seq2_101" value="85"></td>
            <td><input class="mark-cell" name="exam_101" value="90"></td>
            <td><input class="mark-cell" name="mock_101" value=""></td>
            <td><input class="mark-cell" name="practical_101" value=""></td>
            <td><input name="remarks_101" value="great"></td>
          </tr>
          <tr>
            <td><input class="mark-cell" name="seq1_102" value=""></td>
            <td><input class="mark-cell" name="seq2_102" value=""></td>
            <td><input class="mark-cell" name="exam_102" value=""></td>
            <td><input class="mark-cell" name="mock_102" value=""></td>
            <td><input class="mark-cell" name="practical_102" value=""></td>
            <td><input name="remarks_102" value=""></td>
          </tr>
          <tr>
            <td><input class="mark-cell" name="seq1_103" value=""></td>
            <td><input class="mark-cell" name="seq2_103" value=""></td>
            <td><input class="mark-cell" name="exam_103" value=""></td>
            <td><input class="mark-cell" name="mock_103" value=""></td>
            <td><input class="mark-cell" name="practical_103" value=""></td>
            <td><input name="remarks_103" value="comment only"></td>
          </tr>
        </tbody>
      </table>
      <button type="submit" name="" id="save-all-btn">Save All Marks</button>
    </form>`;
  return document.querySelector("form") as HTMLFormElement;
}

describe("rmc-gradebook-wal-enhance", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    delete (window as any).rmcWAL;
    delete (window as any).__rmcGradebookWALBound;
  });

  it("no-ops when rmcWAL is missing", () => {
    const form = buildForm();
    loadScript();
    const event = new Event("submit", { cancelable: true });
    form.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("ships ONE envelope skipping rows with no scores and no remarks", async () => {
    const form = buildForm();
    const append = vi.fn().mockResolvedValue("txn-grade");
    (window as any).rmcWAL = { append, flush: vi.fn(), pending: vi.fn(), onAck: vi.fn() };
    loadScript();
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(append).toHaveBeenCalledTimes(1);
    const [domain, actions] = append.mock.calls[0];
    expect(domain).toBe("grade");
    // Row 102 has no data → skipped. Row 101 (scores+remarks) and 103 (remarks only) ship.
    expect(actions).toHaveLength(2);
    const ids = actions.map((a: any) => a.student_id).sort();
    expect(ids).toEqual(["101", "103"]);
    const row101 = actions.find((a: any) => a.student_id === "101");
    expect(row101.seq1_score).toBe(80);
    expect(row101.exam_score).toBe(90);
    expect(row101.mock_score).toBeNull();
    expect(row101.subject_assignment_id).toBe("33");
    expect(row101.academic_year_id).toBe("11");
    expect(row101.term_id).toBe("22");
  });

  it("does NOT intercept submit when missing year_id or term_id data attrs", () => {
    const form = buildForm({ withYear: false });
    const append = vi.fn();
    (window as any).rmcWAL = { append, flush: vi.fn(), pending: vi.fn(), onAck: vi.fn() };
    loadScript();
    const event = new Event("submit", { cancelable: true });
    form.dispatchEvent(event);
    expect(append).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("falls back to legacy submit on rmcWAL rejection", async () => {
    const form = buildForm();
    const submitSpy = vi.spyOn(form, "submit").mockImplementation(() => {});
    const append = vi.fn().mockRejectedValue(new Error("ws closed"));
    (window as any).rmcWAL = { append, flush: vi.fn(), pending: vi.fn(), onAck: vi.fn() };
    loadScript();
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(submitSpy).toHaveBeenCalled();
  });

  it("preserves legacy 'Submit for Review' path (no intercept)", () => {
    const form = buildForm();
    const reviewBtn = document.createElement("button");
    reviewBtn.type = "submit";
    reviewBtn.setAttribute("name", "action");
    reviewBtn.setAttribute("value", "submit_for_approval");
    form.appendChild(reviewBtn);
    const append = vi.fn();
    (window as any).rmcWAL = { append, flush: vi.fn(), pending: vi.fn(), onAck: vi.fn() };
    loadScript();
    const event = new SubmitEvent("submit", { cancelable: true, submitter: reviewBtn });
    form.dispatchEvent(event);
    expect(append).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });
});
