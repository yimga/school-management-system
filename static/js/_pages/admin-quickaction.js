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

    /* Intelligent Django canvas contract: static save row only — never a floating FAB overlay. */
    if (
      document.querySelector('[data-rmc-django-workspace="change-form"]') ||
      document.querySelector('[data-rmc-admin-canvas-contract="intelligent-full-width"]') ||
      document.querySelector('[data-rmc-shell-root="django-admin"]')
    ) {
      return;
    }

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

  /* v4.00.23 — Page personality auto-detect.
     Sets [data-rmc-page-domain] on <html> before first paint so the CSS
     variables in rmc-page-personality.css resolve. Priority:
       1. Explicit <meta name="rmc-page-domain" content="finance"> in <head>.
       2. body class hint (e.g. "rmc-page-domain-finance").
       3. URL path inference (/admin/finance/... -> "finance").
     The domain attribute on <html> drives accent + glyph + tagline +
     copilot-rail title across every component.
  */
  function detectPageDomain() {
    var html = document.documentElement;
    if (html.getAttribute("data-rmc-page-domain")) return html.getAttribute("data-rmc-page-domain");

    // 1. <meta name="rmc-page-domain">
    var m = document.querySelector('meta[name="rmc-page-domain"]');
    if (m && m.content) return m.content.trim().toLowerCase();

    // 2. body class hint
    var b = document.body;
    if (b && b.className) {
      var match = (b.className.match(/rmc-page-domain-([a-z]+)/) || []);
      if (match[1]) return match[1];
    }

    // 3. URL path inference. Map app names to domains.
    var path = (window.location && window.location.pathname || "").toLowerCase();
    var MAP = [
      [/\/admin\/finance|\/finance|\/billing|\/invoice|\/fee|\/payroll|\/ledger/, "finance"],
      [/\/admin\/people|\/people|\/student|\/teacher|\/parent|\/guardian|\/accounts/, "people"],
      [/\/admin\/evals|\/evals|\/grade|\/curriculum|\/gradebook|\/assessment/, "academic"],
      [/\/admin\/attendance|\/attendance|\/timetable|\/schedule|\/calendar/, "operations"],
      [/\/admin\/admissions|\/admissions|\/intake|\/applicant|\/lead/, "admissions"],
      [/\/admin\/communication|\/communication|\/message|\/notification|\/broadcast/, "comms"],
      [/\/admin\/transport|\/fleet|\/transport|\/route/, "fleet"],
      [/\/admin\/hostel|\/hostel|\/boarding|\/dorm/, "hostel"],
      [/\/admin\/marketplace|\/marketplace|\/integrations?|\/connector/, "marketplace"],
      [/\/admin\/security|\/security|\/compliance|\/audit|\/permission/, "security"],
      [/\/admin\/(siteconfig|tenancy|tenants)|\/admin\/?$|\/admin\/index|\/super\/?$/, "admin"]
    ];
    for (var i = 0; i < MAP.length; i++) {
      if (MAP[i][0].test(path)) return MAP[i][1];
    }
    return "";
  }

  function applyPageDomain() {
    var html = document.documentElement;
    if (html.getAttribute("data-rmc-page-domain")) return;
    var d = detectPageDomain();
    if (d) html.setAttribute("data-rmc-page-domain", d);
  }

  // Apply BEFORE first paint when possible.
  try { applyPageDomain(); } catch (e) {}

  /* v4.00.26 — OS-grade density bootstrap (opt-in only).
     Luxury chrome is the platform baseline; enable only when the operator
     explicitly opts in via localStorage["rmc-os-grade"] = "on" or
     window.rmcOsGrade.set(true). Public API: window.rmcOsGrade.{get,set,toggle}. */
  function applyOsGrade() {
    var html = document.documentElement;
    try {
      if (localStorage.getItem("rmc-os-grade") === "on") {
        html.setAttribute("data-rmc-os-grade", "1");
        return;
      }
    } catch (e) {}
    html.removeAttribute("data-rmc-os-grade");
  }

  function ensureCommandRail() {
    if (document.documentElement.getAttribute("data-rmc-os-grade") !== "1") return;
    if (document.querySelector(".rmc-os-command-rail")) return;
    var rail = document.createElement("div");
    rail.className = "rmc-os-command-rail";
    rail.setAttribute("role", "status");
    rail.setAttribute("aria-live", "polite");
    var domain = document.documentElement.getAttribute("data-rmc-page-domain") || "platform";
    rail.innerHTML =
      '<span class="rmc-os-command-rail__slot">' +
        '<span class="rmc-os-command-rail__dot" aria-hidden="true"></span>' +
        '<span class="rmc-os-command-rail__label">' + domain.toUpperCase() + '</span>' +
      '</span>' +
      '<span class="rmc-os-command-rail__slot">' +
        '<span>SECURE · TLS 1.3</span>' +
      '</span>' +
      '<span class="rmc-os-command-rail__slot rmc-os-command-rail__slot--right">' +
        '<span>DENSITY</span> ' +
        '<kbd class="rmc-os-command-rail__kbd" data-rmc-density-toggle title="Toggle density">D</kbd>' +
        '<span style="margin-left:8px">COMMAND</span> ' +
        '<kbd class="rmc-os-command-rail__kbd">⌘K</kbd>' +
      '</span>';
    document.body.appendChild(rail);

    var k = rail.querySelector("[data-rmc-density-toggle]");
    if (k) k.addEventListener("click", function () {
      if (window.rmcAdminDensity) window.rmcAdminDensity.toggle();
    });
  }

  function dedupAdminSidebar() {
    var seen = Object.create(null);
    var groups = document.querySelectorAll(".admin-sidebar-app-group");
    groups.forEach(function (g) {
      var titleEl = g.querySelector(".admin-sidebar-app-title a, .admin-sidebar-app-title");
      var name = (titleEl ? (titleEl.textContent || "").trim() : "").replace(/\s+/g, " ").toLowerCase();
      if (!name) return;
      if (seen[name]) {
        // Already rendered an identical sidebar app group — remove this dup.
        if (g.parentNode) g.parentNode.removeChild(g);
        return;
      }
      seen[name] = 1;
    });
    // Same defensive dedup for section headings.
    var seenHeadings = Object.create(null);
    var headings = document.querySelectorAll(".admin-sidebar-section-heading");
    headings.forEach(function (h) {
      var n = (h.textContent || "").trim().toLowerCase();
      if (!n) return;
      if (seenHeadings[n]) { if (h.parentNode) h.parentNode.removeChild(h); return; }
      seenHeadings[n] = 1;
    });
  }

  try { applyOsGrade(); } catch (e) {}

  window.rmcOsGrade = {
    get: function () { return document.documentElement.getAttribute("data-rmc-os-grade") === "1"; },
    set: function (on) {
      document.documentElement.setAttribute("data-rmc-os-grade", on ? "1" : "0");
      try { localStorage.setItem("rmc-os-grade", on ? "on" : "off"); } catch (e) {}
    },
    toggle: function () { this.set(!this.get()); return this.get(); }
  };

  /* v4.00.20 — scroll-aware ticker collapse + density-toggle persistence.
     Luxury baseline: comfortable admin density unless operator opts into compact.
     Mirrors to data-rmc-admin-density on <html>. */
  function initShellEnhancements() {
    var html = document.documentElement;

    try {
      var stored = localStorage.getItem("rmc-admin-density");
      if (stored === "compact") {
        html.setAttribute("data-rmc-admin-density", "compact");
      } else {
        html.setAttribute("data-rmc-admin-density", "comfortable");
      }
    } catch (e) {
      html.setAttribute("data-rmc-admin-density", "comfortable");
    }

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
      get: function () { return html.getAttribute("data-rmc-admin-density") || "comfortable"; },
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
    applyPageDomain();
    applyOsGrade();
    init();
    initShellEnhancements();
    initHoverInspector();
    dedupAdminSidebar();
    ensureCommandRail();
  }

  /* v4.00.23 — Hover-row inspector.
     Innovative: hovering any table row for >450ms summons a small
     contextual chip in the bottom-right (just above the floating Save
     cluster) showing key fields from the row. No click needed. Disappears
     when the user moves away or scrolls. Reduces "click row to see
     details" friction in admin changelists.
  */
  function initHoverInspector() {
    var chip = null;
    var hoverTimer = null;
    var lastRow = null;

    function ensureChip() {
      if (chip) return chip;
      chip = document.createElement("div");
      chip.className = "rmc-hover-inspector";
      chip.setAttribute("aria-live", "polite");
      chip.setAttribute("data-state", "hidden");
      document.body.appendChild(chip);
      return chip;
    }

    function summarizeRow(tr) {
      var cells = tr.querySelectorAll("td, th");
      if (!cells.length) return null;
      var fields = [];
      var headRow = tr.closest("table") && tr.closest("table").querySelector("thead tr");
      var headers = headRow ? Array.prototype.slice.call(headRow.querySelectorAll("th")).map(function (h) { return (h.textContent || "").trim(); }) : [];
      for (var i = 0; i < cells.length && fields.length < 4; i++) {
        var v = (cells[i].textContent || "").trim().replace(/\s+/g, " ");
        if (!v || v === "—" || v.length > 96) continue;
        fields.push({ label: headers[i] || ("Col " + (i + 1)), value: v });
      }
      return fields.length ? fields : null;
    }

    function show(tr) {
      var fields = summarizeRow(tr);
      if (!fields) return;
      var c = ensureChip();
      c.innerHTML = "";
      var head = document.createElement("div");
      head.className = "rmc-hover-inspector__head";
      head.textContent = "Inspect";
      c.appendChild(head);
      var list = document.createElement("dl");
      list.className = "rmc-hover-inspector__list";
      fields.forEach(function (f) {
        var dt = document.createElement("dt");
        dt.textContent = f.label;
        var dd = document.createElement("dd");
        dd.textContent = f.value;
        list.appendChild(dt);
        list.appendChild(dd);
      });
      c.appendChild(list);
      c.setAttribute("data-state", "visible");
    }

    function hide() {
      if (chip) chip.setAttribute("data-state", "hidden");
    }

    document.addEventListener("mouseover", function (ev) {
      var tr = ev.target && ev.target.closest && ev.target.closest("#changelist tbody tr, .rmc-data-table tbody tr");
      if (!tr || tr === lastRow) return;
      lastRow = tr;
      if (hoverTimer) clearTimeout(hoverTimer);
      hoverTimer = setTimeout(function () { show(tr); }, 450);
    });
    document.addEventListener("mouseout", function (ev) {
      var tr = ev.target && ev.target.closest && ev.target.closest("#changelist tbody tr, .rmc-data-table tbody tr");
      if (!tr) return;
      if (hoverTimer) clearTimeout(hoverTimer);
      hide();
      lastRow = null;
    });
    window.addEventListener("scroll", hide, { passive: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootAll);
  } else {
    bootAll();
  }
})();
