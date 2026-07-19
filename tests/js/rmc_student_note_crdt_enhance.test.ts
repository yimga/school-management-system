/**
 * Metric 25 — Vitest: student-note CRDT progressive enhancement constructs
 * window.rmcCRDT.Client and pushes LWW ops for data-rmc-crdt-key fields.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT_PATH = path.resolve(
  __dirname,
  "../../static/js/_pages/rmc-student-note-crdt-enhance.js",
);
const SCRIPT_SRC = fs.readFileSync(SCRIPT_PATH, "utf-8");

function loadScript() {
  delete window.__rmcStudentNoteCRDTBound;
  delete window.__rmcStudentNoteCRDTClient;
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT_SRC)();
}

function buildForm() {
  document.body.innerHTML = `
    <form method="post" data-rmc-crdt-entity="student_note">
      <input type="text" name="notes" data-rmc-crdt-key="draft-note-1" value="">
      <button type="submit">Log</button>
    </form>`;
  return document.querySelector("form");
}

describe("rmc-student-note-crdt-enhance", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    delete window.rmcCRDT;
    delete window.__rmcStudentNoteCRDTBound;
    delete window.__rmcStudentNoteCRDTClient;
  });

  it("no-ops when window.rmcCRDT is missing", () => {
    buildForm();
    loadScript();
    expect(window.__rmcStudentNoteCRDTClient).toBeUndefined();
  });

  it("no-ops when form gate is missing", () => {
    document.body.innerHTML = `<form method="post"><input name="notes"></form>`;
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
    const input = document.querySelector("[data-rmc-crdt-key]") as HTMLInputElement;
    input.value = "Follow-up call";
    input.dispatchEvent(new Event("blur"));
    expect(lwwSet).toHaveBeenCalledWith(
      "student_note",
      "draft-note-1",
      "Follow-up call",
    );
    await Promise.resolve();
    expect(pushOps).toHaveBeenCalled();
  });
});
