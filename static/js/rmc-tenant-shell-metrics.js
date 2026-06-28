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
     --rmc-tenant-footer-h     live tenant shell footer height (0 when absent)
     --rmc-tenant-sidebar-inner-h
                               exact available height for the sidebar's own
                               scroll track (canvas workspace height minus the
                               collapse toolbar). The flex height:100% chain
                               does NOT constrain the sidebar column (a flex
                               item that is itself a column flex container grows
                               to content and overflows below the locked body),
                               so the .tp-sidebar-inner scroll track is capped
                               to this measured value — robust across the
                               backend body-class palette rewrite + breakpoints.

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

    /* NOTE (2026-06-28): we intentionally do NOT re-assert `portal-body-with-layout`
       here. The backend theme bootstrap strips it (leaving the palette token), and
       a tempting "fix" is to add it back so the body.portal-body-with-layout CSS
       layer re-scopes. DON'T — that layer has been inactive in production for the
       whole tenant lifetime, and reactivating it regresses live layout (e.g.
       `container-type: inline-size` on .page-wrap collapses the main canvas to a
       2px sliver inside the flex-column main col). The shell fixes are instead
       anchored to stable hooks that survive the strip: the data-rmc-cp-scroll
       attribute (canvas scroll), the #portal-sidebar-col id (rail), and the
       html[data-rmc-tp-v3-shell] prefix (cp-parity item layout). */

    var hh = heightOf(".tp-header");
    if (hh > 24) {
      var px = hh + "px";
      root.style.setProperty("--rmc-tenant-header-h", px);
      root.style.setProperty("--rmc-app-shell-header-h", px);
    }
    var pb = heightOf('[data-shell-chrome="site-preview-banner-top"]');
    root.style.setProperty("--rmc-preview-banner-h", (pb > 0 ? pb : 0) + "px");

    /* Footer height (canvas mode renders .tp-v3-shell-footer as fixed chrome). */
    var fh = heightOf(".tp-v3-shell-footer");
    root.style.setProperty("--rmc-tenant-footer-h", (fh > 0 ? fh : 0) + "px");

    /* Exact sidebar scroll-track height = canvas workspace height minus the
       sidebar's collapse toolbar. Measured (not a percentage chain) because the
       sidebar column cannot be height-constrained by flex here. */
    var workspace = document.querySelector(
      ".tp-v3-shell-workspace, .portal-layout-wrap.tp-v3-shell-workspace"
    );
    var sidebarToolbar = document.querySelector(
      ".portal-sidebar-col .rmc-nav-sidebar__toolbar"
    );
    if (workspace) {
      var wsH = Math.round(workspace.getBoundingClientRect().height);
      /* Main canvas scroll height = the full workspace area. The flex height:100%
         chain does NOT reliably constrain .portal-main-col (same flex-item edge
         case as the sidebar), so on long pages it grows to content height and the
         locked body clips it with no scrollbar. Cap it to this measured value so
         #main-content always scrolls. */
      if (wsH > 80) {
        root.style.setProperty("--rmc-tenant-main-h", wsH + "px");
      }
      var avail = wsH -
        (sidebarToolbar ? Math.round(sidebarToolbar.getBoundingClientRect().height) : 0);
      if (avail > 80) {
        root.style.setProperty("--rmc-tenant-sidebar-inner-h", avail + "px");
      }
    }
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
        var footer = document.querySelector(".tp-v3-shell-footer");
        if (footer) { ro.observe(footer); }
        var workspace = document.querySelector(".tp-v3-shell-workspace, .portal-layout-wrap.tp-v3-shell-workspace");
        if (workspace) { ro.observe(workspace); }
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
