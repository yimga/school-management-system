/**
 * @vitest-environment jsdom
 */

import { beforeEach, describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT_PATH = path.resolve(
  __dirname,
  "../../static/js/rmc-marksheet-device-ocr.js",
);
const SCRIPT_SRC = fs.readFileSync(SCRIPT_PATH, "utf-8");

function loadScript() {
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT_SRC)();
  return (window as any).RMCMarksheetOCR;
}

function gradeForm(delta = true) {
  document.body.innerHTML = `
    <form id="marks-entry-form" data-rmc-ocr-delta-mode="${delta ? "1" : "0"}">
      <table><tbody>
        <tr data-rmc-student-code="STD001">
          <td><input data-rmc-ocr-field="seq1_score" value=""></td>
          <td><input data-rmc-ocr-field="seq2_score" value="9"></td>
          <td><input data-rmc-ocr-field="exam_score" value=""></td>
        </tr>
      </tbody></table>
    </form>`;
  return document.getElementById("marks-entry-form") as HTMLFormElement;
}

describe("device marksheet OCR proposal", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    delete (window as any).RMCMarksheetOCR;
  });

  it("does not parse digits embedded in the student code as scores", () => {
    const api = loadScript();
    const proposal = api.parseLine({
      text: "STD001 12 13 14",
      confidence: 88,
      bbox: { x0: 1, y0: 2, x1: 30, y1: 8 },
    });
    expect(proposal.student_code).toBe("STD001");
    expect(proposal.scores).toEqual({
      seq1_score: 12,
      seq2_score: 13,
      exam_score: 14,
    });
    expect(proposal.bbox.x0).toBe(1);
  });

  it("extracts structured lines with confidence and source coordinates", () => {
    const api = loadScript();
    const proposals = api.proposalsFromData({
      blocks: [
        {
          paragraphs: [
            {
              lines: [
                {
                  text: "STD001 10 11",
                  confidence: 91,
                  bbox: { x0: 4, y0: 5, x1: 50, y1: 15 },
                },
              ],
            },
          ],
        },
      ],
    });
    expect(proposals).toHaveLength(1);
    expect(proposals[0].confidence).toBe(91);
    expect(proposals[0].bbox.y1).toBe(15);
  });

  it("fills proposals but preserves existing values in delta mode", () => {
    const api = loadScript();
    const form = gradeForm(true);
    const summary = api.applyProposals(form, [
      {
        student_code: "STD001",
        scores: { seq1_score: 12, seq2_score: 13, exam_score: 14 },
        invalid: [],
        confidence: 87,
        bbox: { x0: 1, y0: 2, x1: 3, y1: 4 },
      },
      {
        student_code: "MISSING",
        scores: { seq1_score: 10 },
        invalid: [{ field: "seq2_score", value: "99" }],
      },
    ]);
    expect(
      (form.querySelector('[data-rmc-ocr-field="seq1_score"]') as HTMLInputElement)
        .value,
    ).toBe("12");
    expect(
      (form.querySelector('[data-rmc-ocr-field="seq2_score"]') as HTMLInputElement)
        .value,
    ).toBe("9");
    expect(summary.proposed_fields).toBe(2);
    expect(summary.skipped_existing).toBe(1);
    expect(summary.unmatched_students).toBe(1);
    expect(summary.invalid_fields).toBe(1);
  });
});
