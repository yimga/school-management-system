/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT = fs.readFileSync(
  path.resolve(__dirname, "../../static/js/rmc-user-account-center.js"),
  "utf-8",
);

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON() {} };
}

function mount(withRail = true) {
  document.body.innerHTML = `
    <div class="user-dropdown-wrapper">
      <button data-bs-toggle="dropdown">Account</button>
      <div class="rmc-account-center show" data-rmc-account-center="1">
        <span data-rmc-account-connectivity></span>
      </div>
    </div>
    ${withRail ? '<aside data-rmc-copilot-rail></aside>' : ""}
  `;
  const trigger = document.querySelector("button")!;
  trigger.getBoundingClientRect = () => rect(430, 10, 40, 40);
  const rail = document.querySelector("[data-rmc-copilot-rail]");
  if (rail) rail.getBoundingClientRect = () => rect(445, 0, 55, 700);
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 500 });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 700 });
  new Function(SCRIPT)();
  return document.querySelector("[data-rmc-account-center]") as HTMLElement;
}

describe("Account Center viewport positioning", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("moves left of the visible copilot rail", () => {
    const center = mount(true);
    center.closest(".user-dropdown-wrapper")!.dispatchEvent(new Event("shown.bs.dropdown"));
    expect(center.dataset.rmcAccountViewportPositioned).toBe("1");
    expect(center.style.getPropertyValue("--rmc-account-right")).toBe("63px");
    expect(center.style.getPropertyValue("--rmc-account-top")).toBe("58px");
  });

  it("uses the viewport gutter without a copilot and clears on close", () => {
    const center = mount(false);
    const wrapper = center.closest(".user-dropdown-wrapper")!;
    wrapper.dispatchEvent(new Event("shown.bs.dropdown"));
    expect(center.style.getPropertyValue("--rmc-account-right")).toBe("8px");
    wrapper.dispatchEvent(new Event("hidden.bs.dropdown"));
    expect(center.dataset.rmcAccountViewportPositioned).toBeUndefined();
    expect(center.style.getPropertyValue("--rmc-account-right")).toBe("");
  });
});
