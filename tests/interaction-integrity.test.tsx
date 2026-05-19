/**
 * Interaction integrity — DOM contract tests (Vitest + jsdom).
 * Complements Django contract tests and Playwright e2e.
 */
import { describe, expect, it, beforeEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(__dirname, "..");

function read(rel: string): string {
  return readFileSync(resolve(ROOT, rel), "utf-8");
}

describe("interaction integrity templates", () => {
  it("user dropdown includes logout with session-destruction route", () => {
    const html = read("templates/components/user_dropdown.html");
    expect(html).toContain("accounts:logout");
    expect(html).toContain('class="dropdown-item text-danger"');
    expect(html).not.toMatch(/href="#"/);
  });

  it("permission matrix simulator exposes denied banner host", () => {
    const html = read("templates/siteconfig/permission_matrix_simulator.html");
    expect(html).toContain('id="rmc-perm-sim-denied"');
    expect(html).toContain("data-rmc-permission-banner");
  });

  it("503 error pages exist for tenant and control plane", () => {
    expect(read("templates/errors/503.html")).toContain("503");
    expect(read("templates/errors/503_control_plane.html")).toContain("503");
  });
});

describe("RMCInteractionGuard (jsdom)", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <a id="dead" href="#">Dead</a>
      <a id="live" href="/dashboard/">Live</a>
      <div id="toast-container"></div>
    `;
    const guardSrc = read("static/js/rmc-interaction-guard.js");
    // eslint-disable-next-line no-eval
    eval(guardSrc);
  });

  it("exposes guard API on window", () => {
    expect(window.RMCInteractionGuard).toBeDefined();
    expect(window.RMCInteractionGuard?.isDeadHref("#")).toBe(true);
    expect(window.RMCInteractionGuard?.isDeadHref("/ok/")).toBe(false);
  });

  it("blocks dead hash navigation with toast host present", () => {
    window.showToast = vi.fn();
    const dead = document.getElementById("dead") as HTMLAnchorElement;
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    dead.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(window.showToast).toHaveBeenCalled();
  });
});
