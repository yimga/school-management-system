/**
 * admin-quickaction.js — v4.00.19 (2026-05-29)
 *
 * Creative replacement for the old sticky-bottom save bar that was
 * stacking duplicate copies. Mounts a single compact floating cluster
 * in the bottom-right corner with the two most-used actions: Save +
 * Save and continue editing. Appears once the user has scrolled past
 * the first fieldset (signal that they're committed to the form),
 * disappears when the natural-flow submit row scrolls into view (no
 * point in showing both).
 *
 * The full action set (Save and add another, Save as new, Close,
 * Delete) still lives in the natural-flow .rmc-admin-submit-row at the
 * foot of the form; the floating cluster is the thumb-reach shortcut.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var MOUNTED = "data-rmc-admin-quickaction-mounted";
  if (document.documentElement.getAttribute(MOUNTED) === "1") return;

  function init() {
    if (document.documentElement.getAttribute(MOUNTED) === "1") return;
    document.documentElement.setAttribute(MOUNTED, "1");

    var primaryRow = document.querySelector('[data-rmc-admin-submit-row-primary="1"]');
    if (!primaryRow) return;

    var form = primaryRow.closest("form") ||
               document.querySelector('form[id$="_form"]') ||
               document.querySelector('form#changelist-form');
    if (!form) return;

    var saveButton = primaryRow.querySelector('button[name="_save"]');
    var continueButton = primaryRow.querySelector('button[name="_continue"]');
    if (!saveButton && !continueButton) return;

    var cluster = document.createElement("div");
    cluster.className = "rmc-admin-quickaction";
    cluster.setAttribute("role", "group");
    cluster.setAttribute("aria-label", "Quick form actions");

    function makeBtn(label, sourceBtn, secondary) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "rmc-admin-quickaction__btn" + (secondary ? " rmc-admin-quickaction__btn--secondary" : "");
      b.textContent = label;
      b.addEventListener("click", function (ev) {
        ev.preventDefault();
        if (sourceBtn) sourceBtn.click();
      });
      return b;
    }

    if (saveButton) cluster.appendChild(makeBtn("Save", saveButton, false));
    if (continueButton) cluster.appendChild(makeBtn("Save & continue", continueButton, true));

    document.body.appendChild(cluster);

    var anchor = form.querySelector("fieldset") || form.querySelector(".fieldBox") || form;

    function recompute() {
      var anchorRect = anchor.getBoundingClientRect();
      var rowRect = primaryRow.getBoundingClientRect();
      var viewportH = window.innerHeight || document.documentElement.clientHeight;
      var pastAnchor = anchorRect.bottom < viewportH * 0.4;
      var rowVisible = rowRect.top < viewportH && rowRect.bottom > 0;
      var shouldShow = pastAnchor && !rowVisible;
      cluster.setAttribute("data-state", shouldShow ? "visible" : "hidden");
    }

    recompute();
    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () { recompute(); ticking = false; });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });

    // Cmd/Ctrl+S submits the primary form.
    document.addEventListener("keydown", function (ev) {
      var isSave = (ev.metaKey || ev.ctrlKey) && (ev.key === "s" || ev.key === "S");
      if (!isSave) return;
      if (!saveButton) return;
      ev.preventDefault();
      saveButton.click();
    });
  }

  /* v4.00.20 — scroll-aware ticker collapse + density-toggle persistence.
     Sets [data-rmc-scrolled="1"] on <html> once the user scrolls past 64px;
     CSS in admin-manager-shell.css uses that to collapse the LIVE ticker
     into a 4px strip. The density toggle reads localStorage on init and
     mirrors to data-rmc-admin-density on <html>. */
  function initShellEnhancements() {
    var html = document.documentElement;

    try {
      var stored = localStorage.getItem("rmc-admin-density");
      if (stored === "comfortable" || stored === "compact") {
        html.setAttribute("data-rmc-admin-density", stored);
      }
    } catch (e) {}

    var scrolledTicking = false;
    function applyScrolled() {
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      html.setAttribute("data-rmc-scrolled", y > 64 ? "1" : "0");
      scrolledTicking = false;
    }
    function onScroll() {
      if (scrolledTicking) return;
      scrolledTicking = true;
      window.requestAnimationFrame(applyScrolled);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    applyScrolled();

    // Public toggle hook so a menu button can flip density.
    window.rmcAdminDensity = {
      get: function () { return html.getAttribute("data-rmc-admin-density") || "compact"; },
      set: function (mode) {
        if (mode !== "comfortable" && mode !== "compact") return;
        html.setAttribute("data-rmc-admin-density", mode);
        try { localStorage.setItem("rmc-admin-density", mode); } catch (e) {}
      },
      toggle: function () {
        var next = (this.get() === "compact") ? "comfortable" : "compact";
        this.set(next);
        return next;
      }
    };
  }

  function bootAll() {
    init();
    initShellEnhancements();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootAll);
  } else {
    bootAll();
  }
})();
