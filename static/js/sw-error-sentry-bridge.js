/* Pass 11.B closeout — forward Service Worker errors to Sentry-Browser.
 *
 * The SW already broadcasts errors and unhandled rejections to all controlled
 * clients via postMessage({type: "sw-error", ...}) — see static/js/service-worker.js:35,44.
 * This client-side listener picks those up and forwards them to whichever error sink
 * is available (Sentry-Browser if loaded, console otherwise) so production observability
 * captures SW errors instead of swallowing them.
 *
 * Designed to be safe in 4 environments:
 *   1. Sentry-Browser loaded → uses Sentry.captureException with sw_origin tag.
 *   2. Sentry not loaded but window.RUM_BEACON_URL configured → POSTs JSON beacon.
 *   3. Neither configured → console.error so dev can see the message.
 *   4. No navigator.serviceWorker → no-op (older browsers, ie11 fallback).
 */
(function () {
  "use strict";

  if (typeof navigator === "undefined" || !navigator.serviceWorker) return;

  function _captureToSentry(payload) {
    if (typeof window === "undefined" || !window.Sentry) return false;
    try {
      var err = new Error(payload.message || "SW error");
      err.name = "ServiceWorkerError";
      if (payload.stack) {
        err.stack = payload.stack;
      }
      window.Sentry.captureException(err, {
        level: payload.level === "warning" ? "warning" : "error",
        tags: {
          sw_origin: "service-worker",
          sw_url: payload.url || "",
        },
        extra: {
          sw_payload: payload,
        },
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  function _captureToRumBeacon(payload) {
    var url = (window && window.RUM_BEACON_URL) || "";
    if (!url) return false;
    try {
      var body = JSON.stringify({
        kind: "sw-error",
        ts: Date.now(),
        payload: payload,
        page: location.href,
        ua: navigator.userAgent,
      });
      // sendBeacon is non-blocking and survives page unload.
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, body);
      } else {
        fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: body,
          keepalive: true,
        }).catch(function () {});
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  navigator.serviceWorker.addEventListener("message", function (event) {
    if (!event || !event.data || event.data.type !== "sw-error") return;
    var payload = event.data;
    var sent = _captureToSentry(payload);
    if (!sent) {
      sent = _captureToRumBeacon(payload);
    }
    if (!sent && typeof console !== "undefined" && console.error) {
      // Fallback: at least surface in dev tools so developers see it.
      console.error("[SW]", payload.message || payload, payload.stack || "");
    }
  });
})();
