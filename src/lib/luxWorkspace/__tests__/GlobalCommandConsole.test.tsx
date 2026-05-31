import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { PremiumUIOrchestratorProvider, useWorkspaceKernel } from "../WorkspaceKernel";
import { GlobalCommandConsole } from "../GlobalCommandConsole";

function ConsoleOpener() {
  const k = useWorkspaceKernel();
  return <button onClick={() => k.setIsConsoleVisible(true)}>open</button>;
}

function harness() {
  return render(
    <PremiumUIOrchestratorProvider>
      <ConsoleOpener />
      <GlobalCommandConsole />
    </PremiumUIOrchestratorProvider>,
  );
}

describe("GlobalCommandConsole", () => {
  it("is hidden by default; visible after toggle", () => {
    harness();
    expect(screen.queryByRole("dialog", { name: /command console/i })).toBeNull();
    fireEvent.click(screen.getByText("open"));
    expect(screen.getByRole("dialog", { name: /command console/i })).toBeInTheDocument();
  });

  it("filters the listbox by user query", () => {
    harness();
    fireEvent.click(screen.getByText("open"));
    const input = screen.getByRole("searchbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "invoice" } });
    const items = screen.getAllByRole("option");
    expect(items.length).toBeGreaterThan(0);
    const labels = items.map((el) => el.textContent?.toLowerCase() ?? "");
    expect(labels.some((l) => l.includes("invoice"))).toBe(true);
  });

  it("dismisses on backdrop click", () => {
    harness();
    fireEvent.click(screen.getByText("open"));
    const backdrop = screen.getByRole("button", { name: /dismiss command console/i });
    fireEvent.click(backdrop);
    expect(screen.queryByRole("dialog", { name: /command console/i })).toBeNull();
  });

  it("ArrowDown + Enter executes the active option", () => {
    harness();
    fireEvent.click(screen.getByText("open"));
    const input = screen.getByRole("searchbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "log" } });
    act(() => {
      fireEvent.keyDown(input, { key: "ArrowDown" });
      fireEvent.keyDown(input, { key: "Enter" });
    });
    expect(screen.queryByRole("dialog", { name: /command console/i })).toBeNull();
  });
});
