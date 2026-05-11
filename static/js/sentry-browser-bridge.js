/*
 * Pass 11.B: CDN-free Sentry browser bridge.
 *
 * Captures uncaught errors + unhandled promise rejections in the page, and
 * service-worker errors forwarded via postMessage, then POSTs a sanitized
 * payload to /api/observability/client-event/ where the server-side
 * sentry_sdk forwards to the project DSN. This keeps the no-CDN posture
 * (no @sentry/browser bundle on the page) while still closing the
 * observability gap.
 *
 * Includes a small ring buffer so the page can survive a short network
 * outage without losing the most recent errors.
 */
(function () {
  "use strict";

  var ENDPOINT = "/api/observability/client-event/";
  var MAX_QUEUE = 16;
  var queue = [];
  var inflight = false;

  function getCsrfToken() {
    var name = "csrftoken=";
    var parts = (document.cookie || "").split(";");
    for (var i = 0; i < parts.length; i++) {
      var c = parts[i].trim();
      if (c.indexOf(name) === 0) return c.substring(name.length);
    }
    return "";
  }

  function postNext() {
    if (inflight || queue.length === 0) return;
    inflight = true;
    var payload = queue.shift();
    fetch(ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken()
      },
      body: JSON.stringify(payload),
      keepalive: true
    }).catch(function () {
      // On failure, drop — don't loop on a bad endpoint or we'll flood logs.
    }).finally(function () {
      inflight = false;
      if (queue.length) setTimeout(postNext, 250);
    });
  }

  function capture(payload) {
    if (queue.length >= MAX_QUEUE) queue.shift();
    queue.push(payload);
    postNext();
  }

  window.addEventListener("error", function (event) {
    var err = event.error || {};
    capture({
      source: "window",
      level: "error",
      message: String(event.message || err.message || "uncaught error").slice(0, 500),
      url: String(event.filename || location.href).slice(0, 500),
      line: event.lineno || null,
      col: event.colno || null,
      stack: String(err.stack || "").slice(0, 4000)
    });
  });

  window.addEventListener("unhandledrejection", function (event) {
    var reason = event.reason || {};
    capture({
      source: "unhandled_rejection",
      level: "error",
      message: String(reason.message || reason || "unhandled rejection").slice(0, 500),
      url: location.href.slice(0, 500),
      stack: String(reason.stack || "").slice(0, 4000)
    });
  });

  // Bridge SW errors. The service worker postMessages errors to controlled
  // clients; this client forwards them through the same pipeline.
  if (navigator.serviceWorker) {
    navigator.serviceWorker.addEventListener("message", function (event) {
      var data = event.data || {};
      if (data.type !== "sw-error") return;
      capture({
        source: "sw",
        level: data.level || "error",
        message: String(data.message || "service worker error").slice(0, 500),
        url: String(data.url || "").slice(0, 500),
        stack: String(data.stack || "").slice(0, 4000)
      });
    });
  }

  // Expose a tiny manual API for first-party JS to opt-in trace info.
  window.rmcObservability = {
    captureMessage: function (message, level) {
      capture({
        source: "window",
        level: level || "info",
        message: String(message || "").slice(0, 500),
        url: location.href.slice(0, 500)
      });
    }
  };
})();
