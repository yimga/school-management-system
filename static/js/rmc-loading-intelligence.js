/**
 * RunMyCampus Loading Intelligence (v4.04.64) — Surface 5, perceived performance.
 *
 * COMPOSES the loading infrastructure that already exists rather than
 * reinventing it: the top progress bar (rmc-page-progress.js, HTMX + full-page
 * nav bound), the skeleton CSS grammar (.skeleton*), and the form submit
 * pending-state (rmc-form-intelligence.js owns <form method=post> submits).
 *
 * It closes the gaps the audit found:
 *   1. Action pending-state for NON-form buttons/links — opt-in [data-rmc-loading]
 *      (export / preview / save / run / bulk actions) and auto for download links
 *      (a[download]): spinner + aria-busy + optional data-loading-label text swap,
 *      double-activation guard, and the top progress bar — with a watchdog so a
 *      JS/download action that never navigates is never stuck. Page JS can signal
 *      completion early by dispatching `rmc:loading-done` on the element.
 *   2. Skeleton-on-load for async containers — [data-rmc-skeleton="list|card|table
 *      |form|article"]: while an HTMX request targets the element, fill it with a
 *      matching skeleton (HTMX's swap then replaces it on settle).
 *   3. window.RMCLoading helper (busy/idle/skeleton/clear/wrap) for page scripts.
 *
 * Config (default-on) from #rmc-loading-config (SITE cascade). CSP-safe
 * (createElement + textContent, never innerHTML of runtime data). try/catch
 * everywhere; degrades cleanly when the progress bar / HTMX aren't present.
 */
(function () {
  "use strict";

  var WATCHDOG_MS = 8000;
  var SKELETON_LAYOUTS = ["list", "card", "table", "form", "article"];

  var cfg = { intelligence: true, actions: true, skeletons: true };

  function readConfig() {
    var node = document.getElementById("rmc-loading-config");
    if (!node || !node.textContent) { return; }
    try {
      var d = JSON.parse(node.textContent);
      ["intelligence", "actions", "skeletons"].forEach(function (k) {
        if (d[k] === false || d[k] === 0 || d[k] === "0") { cfg[k] = false; }
      });
    } catch (_) {}
  }

  function pageProgress() { return window.RMCPageProgress || null; }

  /* ---------------- action pending-state ---------------- */

  function lock(el) {
    if (el.getAttribute("data-rmc-loading-active") === "1") { return false; }
    el.setAttribute("data-rmc-loading-active", "1");
    el.setAttribute("aria-busy", "true");
    el.classList.add("rmc-loading-busy");
    var label = el.getAttribute("data-loading-label");
    if (label != null && !el.hasAttribute("data-rmc-loading-text") && (el.tagName === "BUTTON" || el.tagName === "A")) {
      el.setAttribute("data-rmc-loading-text", el.textContent || "");
      el.textContent = label;
    }
    var pp = pageProgress();
    if (pp && pp.start) { try { pp.start(); el._rmcLoadingPP = true; } catch (_) {} }
    return true;
  }

  function unlock(el) {
    if (!el || el.getAttribute("data-rmc-loading-active") !== "1") { return; }
    el.removeAttribute("data-rmc-loading-active");
    el.removeAttribute("aria-busy");
    el.classList.remove("rmc-loading-busy");
    if (el.hasAttribute("data-rmc-loading-text")) {
      el.textContent = el.getAttribute("data-rmc-loading-text");
      el.removeAttribute("data-rmc-loading-text");
    }
    if (el._rmcLoadingPP) {
      var pp = pageProgress();
      if (pp && pp.done) { try { pp.done(); } catch (_) {} }
      el._rmcLoadingPP = false;
    }
  }

  function activate(el) {
    if (!lock(el)) { return; }
    setTimeout(function () { unlock(el); }, WATCHDOG_MS);  // never leave it stuck
  }

  // Submit buttons inside a form are owned by rmc-form-intelligence.js — skip
  // them here so a form submit doesn't get two competing pending-states.
  function isFormSubmit(el) {
    var t = (el.getAttribute("type") || "").toLowerCase();
    var isSubmit = t === "submit" || (el.tagName === "BUTTON" && !el.hasAttribute("type"));
    return isSubmit && !!el.form;
  }

  function onClick(e) {
    if (!cfg.actions) { return; }
    var el = e.target && e.target.closest ? e.target.closest("[data-rmc-loading], a[download]") : null;
    if (!el) { return; }
    if (el.getAttribute("data-rmc-loading") === "0") { return; }   // explicit opt-out
    if (el.hasAttribute("disabled")) { return; }
    if (isFormSubmit(el)) { return; }
    if (el.getAttribute("data-rmc-loading-active") === "1") { e.preventDefault(); return; }  // block double
    activate(el);
  }

  /* ---------------- skeleton-on-load (HTMX targets) ---------------- */

  function buildSkeleton(layout) {
    var wrap = document.createElement("div");
    wrap.className = "skeleton-loader rmc-loading-skeleton";
    wrap.setAttribute("aria-hidden", "true");
    function line(cls) { var d = document.createElement("div"); d.className = "skeleton skeleton-text" + (cls ? " " + cls : ""); return d; }
    function block() { var d = document.createElement("div"); d.className = "skeleton skeleton-block"; return d; }
    function circle() { var d = document.createElement("div"); d.className = "skeleton skeleton-circle rmc-loading-skeleton__avatar"; return d; }
    var n, i;
    if (layout === "card") {
      for (n = 0; n < 3; n++) { wrap.appendChild(block()); }
    } else if (layout === "table") {
      for (n = 0; n < 6; n++) { wrap.appendChild(line()); }
    } else if (layout === "form") {
      for (n = 0; n < 4; n++) { wrap.appendChild(block()); }
    } else if (layout === "article") {
      wrap.appendChild(line("")); wrap.appendChild(line("short"));
      for (n = 0; n < 4; n++) { wrap.appendChild(line()); }
    } else { // list (default)
      for (n = 0; n < 5; n++) {
        var row = document.createElement("div");
        row.className = "rmc-loading-skeleton__row";
        row.appendChild(circle());
        var col = document.createElement("div"); col.className = "rmc-loading-skeleton__col";
        col.appendChild(line("")); col.appendChild(line("short"));
        row.appendChild(col);
        wrap.appendChild(row);
      }
    }
    return wrap;
  }

  function showSkeleton(el, layout) {
    if (!el) { return; }
    var lay = SKELETON_LAYOUTS.indexOf(layout) !== -1 ? layout : "list";
    el.setAttribute("aria-busy", "true");
    el.textContent = "";
    el.appendChild(buildSkeleton(lay));
  }
  function clearSkeleton(el) {
    if (!el) { return; }
    el.removeAttribute("aria-busy");
    var sk = el.querySelector(".rmc-loading-skeleton");
    if (sk && sk.parentNode === el) { el.removeChild(sk); }
  }

  function onHtmxBefore(e) {
    if (!cfg.skeletons) { return; }
    var t = e && e.detail && e.detail.target;
    if (!t || !t.getAttribute) { return; }
    var layout = t.getAttribute("data-rmc-skeleton");
    if (!layout) { return; }
    try { showSkeleton(t, layout); } catch (_) {}   // HTMX replaces it on settle
  }

  function init() {
    readConfig();
    if (!cfg.intelligence) { return; }

    document.addEventListener("click", onClick, true);
    document.addEventListener("rmc:loading-done", function (e) {
      if (e && e.target && e.target.nodeType === 1) { unlock(e.target); }
    });
    document.addEventListener("htmx:beforeRequest", onHtmxBefore);

    window.RMCLoading = {
      busy: function (el) { if (el) { activate(el); } },
      idle: function (el) { unlock(el); },
      skeleton: showSkeleton,
      clear: clearSkeleton,
      wrap: function (p) { var pp = pageProgress(); return (pp && pp.promise) ? pp.promise(p) : p; },
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
