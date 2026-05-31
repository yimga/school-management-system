import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { LuxErrorBoundary } from "../LuxErrorBoundary";
import { NetworkStatusChannel } from "../NetworkStatusChannel";
import {
  saveSheetDraft,
  loadSheetDraft,
  clearSheetDraft,
} from "../sheetDraftPersistence";

function Bomb({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error("bomb");
  }
  return <span>safe</span>;
}

describe("LuxErrorBoundary", () => {
  let consoleError: typeof console.error;
  beforeEach(() => {
    consoleError = console.error;
    console.error = () => undefined;
  });
  afterEach(() => {
    console.error = consoleError;
  });

  it("renders children when no error thrown", () => {
    render(
      <LuxErrorBoundary>
        <Bomb shouldThrow={false} />
      </LuxErrorBoundary>,
    );
    expect(screen.getByText("safe")).toBeInTheDocument();
  });

  it("renders fallback + retry button on error; onError called once", () => {
    const onError = vi.fn();
    render(
      <LuxErrorBoundary onError={onError}>
        <Bomb shouldThrow={true} />
      </LuxErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("renders custom fallback label", () => {
    render(
      <LuxErrorBoundary fallbackLabel="Custom oops">
        <Bomb shouldThrow={true} />
      </LuxErrorBoundary>,
    );
    expect(screen.getByText("Custom oops")).toBeInTheDocument();
  });
});

describe("NetworkStatusChannel", () => {
  it("renders nothing while online", () => {
    const { container } = render(<NetworkStatusChannel />);
    expect(container.querySelector(".rmc-lux-netstatus")).toBeNull();
  });

  it("renders offline banner when window fires offline event", () => {
    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      get: () => false,
    });
    render(<NetworkStatusChannel />);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByRole("status").textContent).toMatch(/offline/i);
  });
});

describe("sheetDraftPersistence (localStorage fallback path)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips a draft via the localStorage fallback when IDB is absent", async () => {
    const originalIDB = (globalThis as { indexedDB?: unknown }).indexedDB;
    (globalThis as { indexedDB?: unknown }).indexedDB = undefined;
    try {
      await saveSheetDraft("test-1", "hello world");
      const got = await loadSheetDraft("test-1");
      expect(got?.body).toBe("hello world");
      await clearSheetDraft("test-1");
      expect(await loadSheetDraft("test-1")).toBeNull();
    } finally {
      (globalThis as { indexedDB?: unknown }).indexedDB = originalIDB;
    }
  });
});
