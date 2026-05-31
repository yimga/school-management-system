import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PremiumUIOrchestratorProvider } from "../WorkspaceKernel";
import {
  PremiumInteractiveContainer,
  QuickActionButton,
} from "../PremiumInteractiveContainer";

function wrap(node: React.ReactNode) {
  return render(<PremiumUIOrchestratorProvider>{node}</PremiumUIOrchestratorProvider>);
}

describe("PremiumInteractiveContainer", () => {
  it("renders the hit layer w/ accessible label + fires portal trigger", () => {
    const onPortalTrigger = vi.fn();
    wrap(
      <PremiumInteractiveContainer
        ariaLabel="Open profile for Alice"
        onPortalTrigger={onPortalTrigger}
      >
        <span>Alice content</span>
      </PremiumInteractiveContainer>,
    );
    const hit = screen.getByRole("button", { name: /open profile for alice/i });
    fireEvent.click(hit);
    expect(onPortalTrigger).toHaveBeenCalledTimes(1);
  });

  it("quick action click does not bubble up to the hit layer", () => {
    const onPortalTrigger = vi.fn();
    const onQuick = vi.fn();
    wrap(
      <PremiumInteractiveContainer
        ariaLabel="Card"
        onPortalTrigger={onPortalTrigger}
        quickActionStrip={<QuickActionButton label="Ping" onClick={onQuick} />}
      >
        <span>x</span>
      </PremiumInteractiveContainer>,
    );
    const quick = screen.getByRole("button", { name: /^ping$/i });
    fireEvent.click(quick);
    expect(onQuick).toHaveBeenCalledTimes(1);
    expect(onPortalTrigger).not.toHaveBeenCalled();
  });

  it("applies the active tier + spatial structure as data attributes", () => {
    wrap(
      <PremiumInteractiveContainer
        ariaLabel="Card"
        onPortalTrigger={() => undefined}
        testId="x"
      >
        <span>x</span>
      </PremiumInteractiveContainer>,
    );
    const card = screen.getByTestId("x");
    expect(card.getAttribute("data-lux-tier")).toBe("FINANCIAL_LEDGER");
    expect(card.getAttribute("data-lux-spatial")).toBe("MONOLITHIC_SPLIT_PANE");
  });
});

describe("QuickActionButton", () => {
  it("renders shortcut hint as a kbd element", () => {
    wrap(
      <QuickActionButton label="Invoice" shortcutHint="I" onClick={() => undefined} />,
    );
    expect(screen.getByText("I").tagName.toLowerCase()).toBe("kbd");
  });
});
