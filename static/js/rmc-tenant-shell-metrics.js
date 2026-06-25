/* ============================================================
   rmc-tenant-shell-metrics.js — 2026-06-25
   ------------------------------------------------------------
   Publishes the live tenant header height + site-preview banner height
   into CSS variables so the sticky sidebar (top + height:calc) and the
   fixed AI-copilot rail (top) anchor exactly beneath the pinned chrome
   — no magic numbers, robust across breakpoints / banner toggles.

   Sets on <html>:
     --rmc-tenant-header-h     live .tp-header height
     --rmc-app-shell-header-h  same (the copilot rail's existing var; its
                               usual setter targets .rmc-app-shell which the
                               tenant Bootstrap layout doesn't have)
     --rmc-preview-banner-h    site-preview banner height (0 when absent)

   Self-no-ops on any surface without .tp-header (manager control plane
   uses a different header). CSP-safe: external file, no inline handlers.
   ============================================================ */
(function () {
  "use strict";

  if (typeof document === "undefined") { return; }

  var root = document.documentElement;
  var rafPending = false;

  function heightOf(selector) {
    var el = document.querySelector(selector);
    if (!el) { return 0; }
    return Math.round(el.getBoundingClientRect().height);
  }

  function apply() {
    rafPending = false;
    var hh = heightOf(".tp-header");
    /* Guard a 0/transient measurement (e.g. display:none during a theme
       flip) from clobbering a good value. */
    if (hh > 24) {
      var px = hh + "px";
      root.style.setProperty("--rmc-tenant-header-h", px);
      root.style.setProperty("--rmc-app-shell-header-h", px);
    }
    /* Preview banner (SITE.is_preview) — 0 when absent so the chrome calcs
       collapse to no-offset. */
    var pb = heightOf('[data-shell-chrome="site-preview-banner-top"]');
    root.style.setProperty("--rmc-preview-banner-h", (pb > 0 ? pb : 0) + "px");
  }

  function schedule() {
    if (rafPending) { return; }
    rafPending = true;
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(apply);
    } else {
      apply();
    }
  }

  function boot() {
    var header = document.querySelector(".tp-header");
    if (!header) { return; }
    apply();
    if (typeof window.ResizeObserver === "function") {
      try {
        var ro = new window.ResizeObserver(schedule);
        ro.observe(header);
        var banner = document.querySelector('[data-shell-chrome="site-preview-banner-top"]');
        if (banner) { ro.observe(banner); }
      } catch (_e) { /* fall through to resize listener */ }
    }
    window.addEventListener("resize", schedule, { passive: true });
    window.addEventListener("load", schedule, { passive: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, false);
  } else {
    boot();
  }
})();
