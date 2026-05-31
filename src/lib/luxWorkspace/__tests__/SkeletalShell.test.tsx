import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SkeletalShell, SkeletalDeferred } from "../SkeletalShell";

describe("SkeletalShell", () => {
  it("renders the requested number of items", () => {
    const { container } = render(<SkeletalShell shape="row" count={5} />);
    expect(container.querySelectorAll(".rmc-lux-skeleton__item").length).toBe(5);
  });

  it("clamps count to >= 1", () => {
    const { container } = render(<SkeletalShell shape="card" count={0} />);
    expect(container.querySelectorAll(".rmc-lux-skeleton__item").length).toBe(1);
  });

  it("sets ARIA busy + live region", () => {
    render(<SkeletalShell shape="grid-cell" ariaLabel="Loading grades" />);
    const region = screen.getByRole("status");
    expect(region.getAttribute("aria-busy")).toBe("true");
    expect(region.getAttribute("aria-live")).toBe("polite");
    expect(region.getAttribute("aria-label")).toBe("Loading grades");
  });
});

describe("SkeletalDeferred", () => {
  it("renders fallback while loading and children once done", () => {
    const { rerender } = render(
      <SkeletalDeferred loading={true} fallback={<span data-testid="fb">…</span>}>
        <span data-testid="real">done</span>
      </SkeletalDeferred>,
    );
    expect(screen.getByTestId("fb")).toBeInTheDocument();
    rerender(
      <SkeletalDeferred loading={false} fallback={<span data-testid="fb">…</span>}>
        <span data-testid="real">done</span>
      </SkeletalDeferred>,
    );
    expect(screen.getByTestId("real")).toBeInTheDocument();
    expect(screen.queryByTestId("fb")).toBeNull();
  });
});
