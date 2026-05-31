/**
 * v4.00.9 — Vitest coverage for the AI stream bridge.
 *
 * @vitest-environment jsdom
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";

const SCRIPT_PATH = path.resolve(
  __dirname,
  "../../static/js/_pages/rmc-ai-stream-bridge.js",
);
const SCRIPT_SRC = fs.readFileSync(SCRIPT_PATH, "utf-8");

const AI_CHROME_ISLAND =
  '<script type="application/json" id="page-data-rmc-ai-chrome">' +
  '{"urls":{"ai_stream":"/portal/ai/stream/"}}</script>';

function withAiChromePageData(html: string): string {
  return AI_CHROME_ISLAND + html;
}

function loadScript() {
  delete (window as any).rmcAIStream;
  // eslint-disable-next-line no-new-func
  new Function(SCRIPT_SRC)();
}

describe("rmc-ai-stream-bridge", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-rmc-viewport-class");
    document.head.innerHTML = '<meta name="csrf-token" content="csrf-xyz">';
    document.body.innerHTML = AI_CHROME_ISLAND;
  });

  it("throws when ai_stream URL is missing from page-data", async () => {
    document.body.innerHTML = "";
    (window as any).rmcStreamMount = { attachFetch: vi.fn() };
    loadScript();
    await expect(window.rmcAIStream.send("hello")).rejects.toThrow(/ai_stream URL missing/);
  });

  it("throws when window.rmcStreamMount is missing", async () => {
    delete (window as any).rmcStreamMount;
    loadScript();
    await expect(window.rmcAIStream.send("hello")).rejects.toThrow(/rmcStreamMount unavailable/);
  });

  it("throws when prompt is empty", async () => {
    (window as any).rmcStreamMount = { attachFetch: vi.fn() };
    loadScript();
    await expect(window.rmcAIStream.send("")).rejects.toThrow(/prompt required/);
  });

  it("posts JSON + CSRF + viewport headers and forwards response to attachFetch", async () => {
    document.documentElement.setAttribute("data-rmc-viewport-class", "C");
    const attachFetch = vi.fn().mockResolvedValue(undefined);
    (window as any).rmcStreamMount = { attachFetch };
    const fakeResp = new Response("data: hi\n\n", { status: 200, headers: { "Content-Type": "text/event-stream" } });
    const fetchSpy = vi.spyOn(window as any, "fetch").mockResolvedValue(fakeResp);
    loadScript();
    await window.rmcAIStream.send("what is 2+2", { onComponent: vi.fn() });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/portal/ai/stream/");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.headers["X-CSRFToken"]).toBe("csrf-xyz");
    expect(init.headers["X-RMC-Viewport"]).toBe("C");
    expect(JSON.parse(init.body)).toEqual({ prompt: "what is 2+2" });
    expect(attachFetch).toHaveBeenCalledTimes(1);
    expect(attachFetch.mock.calls[0][0]).toBe(fakeResp);
  });

  it("propagates server errors as Error with status code", async () => {
    (window as any).rmcStreamMount = { attachFetch: vi.fn() };
    vi.spyOn(window as any, "fetch").mockResolvedValue(new Response("nope", { status: 503 }));
    loadScript();
    await expect(window.rmcAIStream.send("hi")).rejects.toThrow(/503/);
  });

  it("bindForm intercepts submit and ships textarea value through send", async () => {
    document.body.innerHTML = withAiChromePageData(`
      <form data-rmc-ai-stream-form="1">
        <textarea name="prompt">Hello AI</textarea>
        <button type="submit">Ask</button>
      </form>`);
    const attachFetch = vi.fn().mockResolvedValue(undefined);
    (window as any).rmcStreamMount = { attachFetch };
    const fetchSpy = vi.spyOn(window as any, "fetch").mockResolvedValue(
      new Response("data: hi\n\n", { status: 200 }),
    );
    loadScript();
    const form = document.querySelector("form") as HTMLFormElement;
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(fetchSpy).toHaveBeenCalled();
    expect(JSON.parse(fetchSpy.mock.calls[0][1].body)).toEqual({ prompt: "Hello AI" });
  });

  it("bindForm falls back to native submit when rmcStreamMount is missing", async () => {
    document.body.innerHTML = `
      <form data-rmc-ai-stream-form="1">
        <textarea name="prompt">Hello</textarea>
        <button type="submit">Ask</button>
      </form>`;
    delete (window as any).rmcStreamMount;
    const fetchSpy = vi.spyOn(window as any, "fetch");
    loadScript();
    const form = document.querySelector("form") as HTMLFormElement;
    const event = new Event("submit", { cancelable: true });
    form.dispatchEvent(event);
    await new Promise((r) => setTimeout(r, 0));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("bindForm is idempotent on the same form", async () => {
    document.body.innerHTML = withAiChromePageData(`
      <form data-rmc-ai-stream-form="1">
        <textarea name="prompt">Hi</textarea>
        <button type="submit">Ask</button>
      </form>`);
    const attachFetch = vi.fn().mockResolvedValue(undefined);
    (window as any).rmcStreamMount = { attachFetch };
    const fetchSpy = vi.spyOn(window as any, "fetch").mockResolvedValue(
      new Response("data: hi\n\n", { status: 200 }),
    );
    loadScript();
    const form = document.querySelector("form") as HTMLFormElement;
    window.rmcAIStream.bindForm(form);
    window.rmcAIStream.bindForm(form);
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("falls back to viewport A when html attr is missing or invalid", async () => {
    document.documentElement.setAttribute("data-rmc-viewport-class", "Z");
    (window as any).rmcStreamMount = { attachFetch: vi.fn().mockResolvedValue(undefined) };
    const fetchSpy = vi.spyOn(window as any, "fetch").mockResolvedValue(
      new Response("data: x", { status: 200 }),
    );
    loadScript();
    await window.rmcAIStream.send("hi");
    expect(fetchSpy.mock.calls[0][1].headers["X-RMC-Viewport"]).toBe("A");
  });
});
