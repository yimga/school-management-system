/**
 * Metric 25 — Vitest: lesson-plan CRDT progressive enhancement constructs
 * window.rmcCRDT.Client and pushes LWW ops for data-rmc-crdt-key fields.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT_PATH = path.resolve(
  __dirname,
  "../../static/js/_pages/rmc-lesson-plan-crdt-enhance.js",
);
const SCRIPT_SRC = fs.readFileSync(SCRIPT_PATH, "utf-8");

function loadScript() {
  delete window.__rmcLessonPlanCRDTBound;
  delete window.__rmcLessonPlanCRDTClient;
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT_SRC)();
}

function buildForm() {
  document.body.innerHTML = `
    <form method="post" data-rmc-crdt-entity="lesson_plan">
      <input type="text" name="title" data-rmc-crdt-key="draft-title" value="">
      <button type="submit">Upload</button>
    </form>`;
  return document.querySelector("form");
}

describe("rmc-lesson-plan-crdt-enhance", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    delete window.rmcCRDT;
    delete window.__rmcLessonPlanCRDTBound;
    delete window.__rmcLessonPlanCRDTClient;
  });

  it("no-ops when window.rmcCRDT is missing", () => {
    buildForm();
    loadScript();
    expect(window.__rmcLessonPlanCRDTClient).toBeUndefined();
  });

  it("no-ops when form gate is missing", () => {
    document.body.innerHTML = `<form method="post"><input name="title"></form>`;
    const Client = vi.fn();
    window.rmcCRDT = { Client };
    loadScript();
    expect(Client).not.toHaveBeenCalled();
  });

  it("constructs Client and pushes LWW on blur", async () => {
    buildForm();
    const pushOps = vi.fn().mockResolvedValue({ applied: 1 });
    const lwwSet = vi.fn();
    window.rmcCRDT = {
      Client: vi.fn().mockImplementation(function () {
        this.lwwSet = lwwSet;
        this.pushOps = pushOps;
      }),
    };
    loadScript();
    expect(window.rmcCRDT.Client).toHaveBeenCalled();
    const input = document.querySelector("[data-rmc-crdt-key]");
    input.value = "Week 3 algebra";
    input.dispatchEvent(new Event("blur"));
    expect(lwwSet).toHaveBeenCalledWith(
      "lesson_plan",
      "draft-title",
      "Week 3 algebra",
    );
    expect(pushOps).toHaveBeenCalled();
  });
});
