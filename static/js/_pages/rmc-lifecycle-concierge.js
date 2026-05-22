/*
 * rmc-lifecycle-concierge.js
 *
 * Tiny dismiss handler for the Lifecycle Concierge band. Idempotent:
 * sets dataset.rmcConciergeInited so HTMX / Turbo partial swaps don't
 * double-bind the click listener.
 *
 * Honors sessionStorage so dismissals persist within a tab session
 * without server round-trips.
 *
 * v3.61.2 (2026-05-22): Wave L3.
 */
(function () {
  "use strict";

  var SESSION_KEY = "rmc-lifecycle-concierge-dismissed";

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  ready(function () {
    var band = document.querySelector("[data-lifecycle-concierge]");
    if (!band) return;
    if (band.dataset.rmcConciergeInited === "1") return;
    band.dataset.rmcConciergeInited = "1";

    // Honor prior dismissal in this tab session.
    try {
      if (window.sessionStorage && window.sessionStorage.getItem(SESSION_KEY) === "1") {
        band.setAttribute("data-dismissed", "1");
        return;
      }
    } catch (e) { /* sessionStorage may be blocked; safe to ignore */ }

    var btn = band.querySelector("[data-lifecycle-concierge-dismiss]");
    if (!btn) return;
    btn.addEventListener("click", function () {
      band.setAttribute("data-dismissed", "1");
      try {
        if (window.sessionStorage) {
          window.sessionStorage.setItem(SESSION_KEY, "1");
        }
      } catch (e) { /* safe to ignore */ }
    });
  });
})();
