/**
 * Marketing FOUC-safe theme bootstrap — runs synchronously in <head> before CSS paint.
 *
 * Storage: `rmc-mkt-theme` (anonymous marketing visitors). Falls back to
 * `runmycampus-theme-preference` when a logged-in user arrives from portal/admin.
 *
 * v3 contract: `data-theme` / `data-bs-theme` / `data-resolved-theme` always carry
 * the effective theme (light|dark), never "system". Raw preference → data-theme-preference.
 */
(function () {
  "use strict";
  var MKT_KEY = "rmc-mkt-theme";
  var PLATFORM_KEY = "runmycampus-theme-preference";
  var VALID = { light: 1, dark: 1, system: 1 };
  var mql = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  var root = document.documentElement;

  function readRaw() {
    var raw = null;
    try {
      raw = localStorage.getItem(MKT_KEY);
      if (!VALID[raw]) {
        raw = localStorage.getItem(PLATFORM_KEY);
      }
    } catch (_) {
      raw = null;
    }
    return VALID[raw] ? raw : "light";
  }

  function resolve(pref) {
    if (pref === "system") {
      return mql && mql.matches ? "dark" : "light";
    }
    return pref;
  }

  function apply(pref) {
    var resolved = resolve(pref);
    root.setAttribute("data-theme-preference", pref);
    root.setAttribute("data-theme", resolved);
    root.setAttribute("data-resolved-theme", resolved);
    root.setAttribute("data-bs-theme", resolved);
    root.style.colorScheme = resolved;
    if (resolved === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
  }

  apply(readRaw());
})();
