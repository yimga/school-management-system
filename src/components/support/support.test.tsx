import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SupportErrorBoundary } from "./SupportErrorBoundary";

function BrokenChild(): never {
  throw new Error("boom");
}

describe("SupportErrorBoundary", () => {
  it("renders fallback when a child throws", () => {
    render(
      <SupportErrorBoundary surface="kb">
        <BrokenChild />
      </SupportErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveAttribute(
      "data-rmc-support-error-boundary-fallback",
      "1",
    );
    expect(screen.getByText(/Help assistant unavailable/i)).toBeTruthy();
  });

  it("renders children when healthy", () => {
    render(
      <SupportErrorBoundary>
        <p>OK</p>
      </SupportErrorBoundary>,
    );
    expect(screen.getByText("OK")).toBeTruthy();
  });
});
