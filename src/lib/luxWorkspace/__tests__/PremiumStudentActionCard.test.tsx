import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PremiumUIOrchestratorProvider } from "../WorkspaceKernel";
import { PremiumStudentActionCard } from "../PremiumStudentActionCard";

function wrap(node: React.ReactNode) {
  return render(<PremiumUIOrchestratorProvider>{node}</PremiumUIOrchestratorProvider>);
}

describe("PremiumStudentActionCard", () => {
  it("opens the detail sheet on card portal trigger + closes via backdrop", () => {
    wrap(
      <PremiumStudentActionCard
        id="stu-001"
        firstName="John"
        lastName="Doe"
        cycleLabel="Form 5 · Science"
        ledgerStatus="PAID"
        performanceMark="89%"
      />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /open profile workspace for john doe/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close detail sheet/i }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("fires onInvoice when the quick Invoice button is clicked", () => {
    const onInvoice = vi.fn();
    wrap(
      <PremiumStudentActionCard
        id="stu-002"
        firstName="Jane"
        lastName="Smith"
        cycleLabel="Form 3"
        ledgerStatus="OVERDUE"
        performanceMark="72%"
        onInvoice={onInvoice}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^invoice$/i }));
    expect(onInvoice).toHaveBeenCalledWith("stu-002");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders correct status chip class for each ledger state", () => {
    const { rerender, container } = render(
      <PremiumUIOrchestratorProvider>
        <PremiumStudentActionCard
          id="s"
          firstName="A"
          lastName="B"
          cycleLabel="x"
          ledgerStatus="PENDING"
          performanceMark="0"
        />
      </PremiumUIOrchestratorProvider>,
    );
    expect(container.querySelector(".rmc-lux-status--pending")).not.toBeNull();
    rerender(
      <PremiumUIOrchestratorProvider>
        <PremiumStudentActionCard
          id="s"
          firstName="A"
          lastName="B"
          cycleLabel="x"
          ledgerStatus="OVERDUE"
          performanceMark="0"
        />
      </PremiumUIOrchestratorProvider>,
    );
    expect(container.querySelector(".rmc-lux-status--overdue")).not.toBeNull();
  });
});
