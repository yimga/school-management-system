import { describe, it, expect, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { PremiumUIOrchestratorProvider } from "../WorkspaceKernel";
import { CustomKeyboardShortcutBus } from "../CustomKeyboardShortcutBus";

function dispatchKey(opts: { key: string; meta?: boolean; ctrl?: boolean; target?: Element }) {
  const ev = new KeyboardEvent("keydown", {
    key: opts.key,
    metaKey: !!opts.meta,
    ctrlKey: !!opts.ctrl,
    bubbles: true,
    cancelable: true,
  });
  (opts.target ?? window).dispatchEvent(ev);
  return ev;
}

describe("CustomKeyboardShortcutBus", () => {
  it("Cmd+K toggles the command console + dispatches OPEN_COMMAND_CONSOLE", () => {
    const onAction = vi.fn();
    render(
      <PremiumUIOrchestratorProvider onAction={onAction}>
        <CustomKeyboardShortcutBus />
      </PremiumUIOrchestratorProvider>,
    );
    act(() => {
      dispatchKey({ key: "k", meta: true });
    });
    expect(onAction).toHaveBeenCalledWith("OPEN_COMMAND_CONSOLE", "keyboard");
  });

  it("tier-local key fires the tier-specific action", () => {
    const onAction = vi.fn();
    render(
      <PremiumUIOrchestratorProvider onAction={onAction}>
        <CustomKeyboardShortcutBus />
      </PremiumUIOrchestratorProvider>,
    );
    act(() => {
      dispatchKey({ key: "i" });
    });
    expect(onAction).toHaveBeenCalledWith("SPAWN_CONTEXTUAL_INVOICE_PANEL", "keyboard");
  });

  it("ignores tier-local keys while typing in an INPUT", () => {
    const onAction = vi.fn();
    render(
      <PremiumUIOrchestratorProvider onAction={onAction}>
        <CustomKeyboardShortcutBus />
        <input data-testid="typing" />
      </PremiumUIOrchestratorProvider>,
    );
    const input = screen.getByTestId("typing");
    act(() => {
      input.focus();
      dispatchKey({ key: "i", target: input });
    });
    expect(onAction).not.toHaveBeenCalled();
  });

  it("ignores tier-local keys while typing in a contenteditable", () => {
    const onAction = vi.fn();
    render(
      <PremiumUIOrchestratorProvider onAction={onAction}>
        <CustomKeyboardShortcutBus />
        <div data-testid="edit" contentEditable suppressContentEditableWarning>
          x
        </div>
      </PremiumUIOrchestratorProvider>,
    );
    const ed = screen.getByTestId("edit");
    act(() => {
      ed.focus();
      dispatchKey({ key: "i", target: ed });
    });
    expect(onAction).not.toHaveBeenCalled();
  });

  it("never fires a tier-local action belonging to a different tier", () => {
    const onAction = vi.fn();
    render(
      <PremiumUIOrchestratorProvider onAction={onAction}>
        <CustomKeyboardShortcutBus />
      </PremiumUIOrchestratorProvider>,
    );
    act(() => {
      dispatchKey({ key: "s" });
    });
    expect(onAction).not.toHaveBeenCalled();
  });

  it("cleans up window listener on unmount (no leak)", () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(
      <PremiumUIOrchestratorProvider>
        <CustomKeyboardShortcutBus />
      </PremiumUIOrchestratorProvider>,
    );
    const addCount = add.mock.calls.filter((c) => c[0] === "keydown").length;
    unmount();
    const removeCount = remove.mock.calls.filter((c) => c[0] === "keydown").length;
    expect(removeCount).toBe(addCount);
    add.mockRestore();
    remove.mockRestore();
  });
});
