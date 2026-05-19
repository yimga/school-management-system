/**
 * Dual-dashboard topology — React error boundary + template contracts.
 */
import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { DashboardErrorBoundary } from "../src/apps/dashboard/ErrorBoundary";

const ROOT = resolve(__dirname, "..");

function read(rel: string): string {
  return readFileSync(resolve(ROOT, rel), "utf-8");
}

describe("dashboard topology templates", () => {
  it("denied page explains operational vs configuration split", () => {
    const html = read("templates/errors/dashboard_topology_denied.html");
    expect(html).toContain("Configuration area restricted");
    expect(html).toContain("operational dashboard");
  });

  it("widget boundary partial exposes retry control", () => {
    const html = read("templates/components/dashboard_widget_error_boundary.html");
    expect(html).toContain("data-widget-retry");
    expect(html).toContain("data-dashboard-error-boundary");
    expect(html).toContain("data-rmc-shell-viewport-safe");
  });

  it("widget boundary script ships retry event", () => {
    const js = read("static/js/rmc-dashboard-widget-boundary.js");
    expect(js).toContain("rmc-dashboard-widget-retry");
  });
});

describe("DashboardErrorBoundary", () => {
  function Thrower() {
    throw new Error("viz feed down");
  }

  it("renders retry control after child failure", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <DashboardErrorBoundary name="Revenue" tenantId="demo-school">
        <Thrower />
      </DashboardErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/Retry connection/i)).toBeTruthy();
    fireEvent.click(screen.getByText(/Retry connection/i));
    spy.mockRestore();
  });
});
