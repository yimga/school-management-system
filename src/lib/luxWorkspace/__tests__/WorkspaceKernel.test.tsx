import { describe, it, expect, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { PremiumUIOrchestratorProvider, useWorkspaceKernel } from "../WorkspaceKernel";

function Probe() {
  const k = useWorkspaceKernel();
  return (
    <div>
      <span data-testid="tier">{k.activeTier}</span>
      <span data-testid="label">{k.tier.label}</span>
      <span data-testid="depth">{k.topOverlayStack.length}</span>
      <button onClick={() => k.setActiveTier("ACADEMIC_MATRIX")}>switch</button>
      <button onClick={() => k.pushOverlay("p1")}>push</button>
      <button onClick={() => k.popOverlay()}>pop</button>
      <button onClick={() => k.dispatch("RUN_X", "click")}>dispatch</button>
    </div>
  );
}

describe("WorkspaceKernel", () => {
  it("throws when used outside provider", () => {
    const orig = console.error;
    console.error = () => undefined;
    expect(() => render(<Probe />)).toThrow(/PremiumUIOrchestratorProvider/);
    console.error = orig;
  });

  it("provides the initial tier and reflects setActiveTier", () => {
    render(
      <PremiumUIOrchestratorProvider>
        <Probe />
      </PremiumUIOrchestratorProvider>,
    );
    expect(screen.getByTestId("tier").textContent).toBe("FINANCIAL_LEDGER");
    expect(screen.getByTestId("label").textContent).toBe("Financial Ledger");

    act(() => {
      screen.getByText("switch").click();
    });
    expect(screen.getByTestId("tier").textContent).toBe("ACADEMIC_MATRIX");
    expect(document.documentElement.getAttribute("data-lux-tier")).toBe("ACADEMIC_MATRIX");
  });

  it("manages overlay stack push/pop", () => {
    render(
      <PremiumUIOrchestratorProvider>
        <Probe />
      </PremiumUIOrchestratorProvider>,
    );
    expect(screen.getByTestId("depth").textContent).toBe("0");
    act(() => {
      screen.getByText("push").click();
    });
    expect(screen.getByTestId("depth").textContent).toBe("1");
    act(() => {
      screen.getByText("pop").click();
    });
    expect(screen.getByTestId("depth").textContent).toBe("0");
  });

  it("dispatches actions to onAction handler", () => {
    const onAction = vi.fn();
    render(
      <PremiumUIOrchestratorProvider onAction={onAction}>
        <Probe />
      </PremiumUIOrchestratorProvider>,
    );
    act(() => {
      screen.getByText("dispatch").click();
    });
    expect(onAction).toHaveBeenCalledWith("RUN_X", "click");
  });

  it("applies CSS custom properties for spring + duration + touch target", () => {
    const { container } = render(
      <PremiumUIOrchestratorProvider>
        <div>x</div>
      </PremiumUIOrchestratorProvider>,
    );
    const root = container.querySelector(".rmc-lux-root") as HTMLElement;
    expect(root).not.toBeNull();
    expect(root.style.getPropertyValue("--lux-spring-curve")).toContain("cubic-bezier");
    expect(root.style.getPropertyValue("--lux-min-touch-target")).toBe("48px");
  });
});
