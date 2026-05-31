import { describe, it, expect } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { useRef, useState } from "react";
import { useFocusTrap } from "../useFocusTrap";

function Trapped({ active }: { active: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap({ active, ref });
  return (
    <div ref={ref} data-testid="container">
      <button data-testid="a">A</button>
      <button data-testid="b">B</button>
      <button data-testid="c">C</button>
    </div>
  );
}

function Harness() {
  const [active, setActive] = useState(false);
  return (
    <>
      <button data-testid="outside" onClick={() => setActive(true)}>open</button>
      {active ? <Trapped active={active} /> : null}
    </>
  );
}

describe("useFocusTrap", () => {
  it("focuses the first focusable element on activation", () => {
    render(<Harness />);
    act(() => {
      screen.getByTestId("outside").click();
    });
    expect(document.activeElement).toBe(screen.getByTestId("a"));
  });

  it("wraps Tab from last back to first", () => {
    render(<Harness />);
    act(() => {
      screen.getByTestId("outside").click();
    });
    act(() => {
      screen.getByTestId("c").focus();
    });
    expect(document.activeElement).toBe(screen.getByTestId("c"));
    act(() => {
      fireEvent.keyDown(document, { key: "Tab" });
    });
    expect(document.activeElement).toBe(screen.getByTestId("a"));
  });

  it("wraps Shift+Tab from first back to last", () => {
    render(<Harness />);
    act(() => {
      screen.getByTestId("outside").click();
    });
    expect(document.activeElement).toBe(screen.getByTestId("a"));
    act(() => {
      fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    });
    expect(document.activeElement).toBe(screen.getByTestId("c"));
  });
});
