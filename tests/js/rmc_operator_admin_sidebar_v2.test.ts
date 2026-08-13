/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT = fs.readFileSync(
  path.resolve(__dirname, "../../static/js/rmc-operator-admin-sidebar-v2.js"),
  "utf-8",
);

function mount() {
  document.body.className = "admin-manager-shell";
  document.body.innerHTML = `
    <nav data-rmc-operator-admin-sidebar-v2="1">
      <input id="rmcOperatorAdminNavSearch">
      <p id="rmcOperatorAdminNavSearchStatus"></p>
      <span data-operator-connection-status><i></i><span data-operator-connection-label></span></span>
      <div class="cp-sidebar__group"><a class="cp-sidebar__item" href="/admin/tenants/"><span class="cp-nav-label">Tenants</span></a></div>
      <div class="cp-sidebar__group"><a class="cp-sidebar__item" href="/admin/registry/"><span class="cp-nav-label">Global registries</span></a></div>
      <div data-operator-recent-wrap hidden><button data-operator-recent-clear></button><div data-operator-recent-list></div></div>
    </nav>`;
  new Function(SCRIPT)();
  return document.querySelector("[data-rmc-operator-admin-sidebar-v2]") as HTMLElement;
}

describe("operator admin sidebar v2", () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.className = "";
    document.body.innerHTML = "";
  });

  it("filters destinations and announces the match count", () => {
    const root = mount();
    const input = root.querySelector("#rmcOperatorAdminNavSearch") as HTMLInputElement;
    input.value = "registry";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    const links = root.querySelectorAll("a.cp-sidebar__item");
    expect(links[0].hasAttribute("data-operator-search-hidden")).toBe(true);
    expect(links[1].hasAttribute("data-operator-search-hidden")).toBe(false);
    expect(root.querySelector("#rmcOperatorAdminNavSearchStatus")!.textContent).toBe("1 matching destination");
  });

  it("focuses search with slash and exposes local-ready status", () => {
    const root = mount();
    const input = root.querySelector("#rmcOperatorAdminNavSearch") as HTMLInputElement;
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true }));
    expect(document.activeElement).toBe(input);
    expect(root.querySelector("[data-operator-connection-label]")!.textContent).toBe("Local ready");
  });
});
