/**
 * rmc-mkt-local-first-band.js
 *
 * v3.62.10 (2026-05-22) — Wave 9 local-first marketing band.
 *
 * Wire the dismiss button so once the visitor closes the band, it stays
 * dismissed for 14 days per country code (so picking a new country in a
 * geo/picker session shows the band again for the new country).
 *
 * CSP-safe IIFE, idempotent (no re-binding), fail-soft (every read/write to
 * localStorage is try/catch — incognito / Safari-strict mode safe).
 */
(function () {
  "use strict";

  var INIT_FLAG = "rmcLocalFirstBandInited";
  var STORAGE_KEY = "rmc.localFirstBand.dismissed";
  var TTL_DAYS = 14;

  function nowSec() { return Math.floor(Date.now() / 1000); }

  function readDismissalMap() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return (parsed && typeof parsed === "object") ? parsed : {};
    } catch (_e) {
      return {};
    }
  }

  function writeDismissalMap(map) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
    } catch (_e) {
      /* incognito / quota / strict-mode — swallow */
    }
  }

  function isCountryDismissed(cc) {
    if (!cc) return false;
    var map = readDismissalMap();
    var entry = map[cc];
    if (!entry || typeof entry.until !== "number") return false;
    return entry.until > nowSec();
  }

  function markCountryDismissed(cc) {
    if (!cc) return;
    var map = readDismissalMap();
    map[cc] = { until: nowSec() + TTL_DAYS * 86400 };
    writeDismissalMap(map);
  }

  function init() {
    if (document.documentElement.dataset[INIT_FLAG] === "1") return;
    document.documentElement.dataset[INIT_FLAG] = "1";

    var band = document.querySelector("[data-rmc-local-first-band]");
    if (!band) return;
    var cc = (band.getAttribute("data-rmc-country") || "").toUpperCase();

    // Hide pre-paint if already dismissed for this country.
    if (cc && isCountryDismissed(cc)) {
      band.hidden = true;
      return;
    }

    var closeBtn = band.querySelector("[data-rmc-local-band-dismiss]");
    if (!closeBtn) return;
    closeBtn.addEventListener("click", function (ev) {
      ev.preventDefault();
      band.hidden = true;
      markCountryDismissed(cc);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
