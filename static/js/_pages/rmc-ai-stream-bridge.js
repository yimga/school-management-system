// v4.00.9 — Thin bridge from "AI surfaces" to the streaming gateway view.
//
// Posts to the named portal:ai_stream URL from page-data-rmc-ai-chrome and hands
// the streaming response to window.rmcStreamMount.attachFetch.
//
// API surface (window.rmcAIStream):
//   send(prompt, opts) -> Promise<void>
//     opts:
//       - viewport: optional A|B|C override (default: read from <html data-rmc-viewport-class>)
//       - onComponent(name, rootEl)
//       - onChunkText(text, mountedComponent)
//       - onComplete(buffer, mountedComponent)
//
// When window.rmcStreamMount is missing this script is a no-op.

(function () {
  "use strict";
  if (window.rmcAIStream) return;

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const cookie = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
  }

  function aiStreamUrl() {
    const el = document.getElementById("page-data-rmc-ai-chrome");
    if (!el) return "";
    try {
      const cfg = JSON.parse(el.textContent || "{}");
      const u = cfg.urls && cfg.urls.ai_stream;
      return u && String(u).length ? String(u) : "";
    } catch (_e) {
      return "";
    }
  }

  function currentViewport() {
    const v = document.documentElement.getAttribute("data-rmc-viewport-class");
    return v && /^[ABC]$/.test(v) ? v : "A";
  }

  async function send(prompt, opts) {
    opts = opts || {};
    if (!prompt || typeof prompt !== "string") {
      throw new Error("rmcAIStream.send: prompt required");
    }
    if (!window.rmcStreamMount || typeof window.rmcStreamMount.attachFetch !== "function") {
      throw new Error("rmcAIStream.send: rmcStreamMount unavailable");
    }
    const streamUrl = aiStreamUrl();
    if (!streamUrl) {
      throw new Error("rmcAIStream.send: ai_stream URL missing from page-data-rmc-ai-chrome");
    }
    const viewport = opts.viewport || currentViewport();
    const response = await fetch(streamUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-RMC-Viewport": viewport,
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ prompt }),
    });
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(`rmcAIStream.send: ${response.status} ${text}`);
    }
    return await window.rmcStreamMount.attachFetch(response, {
      onComponent: opts.onComponent,
      onChunkText: opts.onChunkText,
      onComplete: opts.onComplete,
    });
  }

  /**
   * Opt-in form binding. Any template can drop:
   *
   *   <form data-rmc-ai-stream-form="1" data-rmc-ai-stream-target="my-target">
   *     <textarea name="prompt"></textarea>
   *     <button type="submit">Ask</button>
   *     <div data-rmc-stream-target="my-target"></div>
   *   </form>
   *
   * and the bridge will intercept submit, ship the textarea value through the
   * streaming gateway, and progressively mount fragments inside the target.
   * Falls back to native form submission when rmcStreamMount is unavailable.
   */
  function bindForm(form, opts) {
    if (!form || form.__rmcAIBound) return;
    form.__rmcAIBound = true;
    opts = opts || {};
    form.addEventListener("submit", function (ev) {
      const ta = form.querySelector('textarea[name="prompt"], input[name="prompt"]');
      const prompt = (ta && ta.value ? ta.value : "").trim();
      if (!prompt) return;
      if (!window.rmcStreamMount) return;
      ev.preventDefault();
      send(prompt, {
        onComponent: opts.onComponent,
        onChunkText: opts.onChunkText,
        onComplete: opts.onComplete,
      }).catch(function (err) {
        if (typeof opts.onError === "function") {
          try {
            opts.onError(err);
          } catch (_e) {}
        }
      });
    });
  }

  function autoBindOptInForms() {
    const forms = document.querySelectorAll('form[data-rmc-ai-stream-form="1"]');
    forms.forEach((f) => bindForm(f));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoBindOptInForms, { once: true });
  } else {
    autoBindOptInForms();
  }

  window.rmcAIStream = { send, bindForm };
})();
