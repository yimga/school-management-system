/**
 * @vitest-environment jsdom
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT = fs.readFileSync(
  path.resolve(__dirname, "../../static/js/rmc-layout-observer.js"),
  "utf-8",
);

class FakeResizeObserver {
  callback: ResizeObserverCallback;
  observed: Element[] = [];

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(element: Element) {
    this.observed.push(element);
  }

  disconnect() {}
  unobserve() {}
}

function dimensions(
  element: Element,
  values: { clientWidth: number; scrollWidth: number; clientHeight: number; scrollHeight: number },
) {
  Object.entries(values).forEach(([key, value]) => {
    Object.defineProperty(element, key, { configurable: true, value });
  });
}

function load() {
  new Function(SCRIPT)();
  document.dispatchEvent(new Event("DOMContentLoaded"));
}

describe("bounded layout observer", () => {
  beforeEach(() => {
    if ((window as any).rmcLayoutObserver) {
      (window as any).rmcLayoutObserver.stop();
    }
    document.documentElement.setAttribute("data-rmc-viewport-class", "B");
    document.documentElement.setAttribute("dir", "rtl");
    document.body.innerHTML = "";
    delete (window as any).rmcLayoutObserver;
    (window as any).ResizeObserver = FakeResizeObserver;
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0);
      return 1;
    });
  });

  afterEach(() => {
    if ((window as any).rmcLayoutObserver) {
      (window as any).rmcLayoutObserver.stop();
    }
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("reports aggregate overflow without content or selectors", () => {
    const surface = document.createElement("div");
    surface.className = "table-responsive";
    surface.textContent = "Private student record";
    dimensions(surface, {
      clientWidth: 300,
      scrollWidth: 420,
      clientHeight: 100,
      scrollHeight: 100,
    });
    document.body.appendChild(surface);

    load();
    const snapshot = (window as any).rmcLayoutObserver.getSnapshot();

    expect(snapshot).toMatchObject({
      version: 1,
      observed_count: 1,
      overflow_count: 1,
      inline_overflow_count: 1,
      max_inline_overflow_px: 120,
      viewport_class: "B",
      direction: "rtl",
    });
    expect(JSON.stringify(snapshot)).not.toContain("Private student");
    expect(JSON.stringify(snapshot)).not.toContain("table-responsive");
    expect(surface.getAttribute("data-rmc-layout-overflow")).toBe("inline");
  });

  it("does not mutate presentation styles or shrink text", () => {
    const surface = document.createElement("section");
    surface.setAttribute("data-rmc-layout-observe", "clip");
    surface.style.fontSize = "18px";
    dimensions(surface, {
      clientWidth: 200,
      scrollWidth: 200,
      clientHeight: 100,
      scrollHeight: 150,
    });
    document.body.appendChild(surface);

    load();
    const snapshot = (window as any).rmcLayoutObserver.getSnapshot();

    expect(snapshot.block_overflow_count).toBe(1);
    expect(snapshot.max_block_overflow_px).toBe(50);
    expect(surface.style.fontSize).toBe("18px");
    expect(surface.style.transform).toBe("");
    expect(surface.style.zoom || "").toBe("");
  });
});
