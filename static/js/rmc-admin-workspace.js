/**
 * rmc-admin-workspace.js
 * - Builds the change-form "On this page" rail nav from fieldsets (scroll-spy).
 * - Honest Form / Audit view toggle (intelligent canvas contract).
 * - Changelist rail filter trigger.
 */
(function () {
  "use strict";

  var VIEW_KEY = "rmc-django-view-mode";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function sectionLabel(sec, index) {
    var h = sec.querySelector(
      ":scope > h2, :scope > details > summary, :scope > .inline-heading, :scope > h3"
    );
    if (!h) h = sec.querySelector("h2, h3, summary");
    var label = h ? (h.textContent || "").replace(/\s+/g, " ").trim() : "";
    if (!label) label = index === 0 ? "General" : "Section " + (index + 1);
    return label.length > 42 ? label.slice(0, 41) + "…" : label;
  }

  function closePreviewDrawer(drawer) {
    var target = drawer || document.getElementById("rmc-django-preview-drawer");
    if (target) target.setAttribute("hidden", "");
    document.querySelectorAll(".rmc-mv-preview-drawer:not(#rmc-django-preview-drawer)").forEach(function (el) {
      el.setAttribute("hidden", "");
    });
  }

  function setViewMode(workspace, mode) {
    if (!workspace || !mode) return;
    // Staged/fake Preview mode removed — only Form + Audit are honest.
    if (mode === "preview") mode = "form";
    var allowed = { form: 1, audit: 1 };
    if (!allowed[mode]) mode = "form";
    workspace.setAttribute("data-rmc-django-view-mode", mode);
    try {
      sessionStorage.setItem(VIEW_KEY, mode);
    } catch (_e) {
      /* ignore */
    }

    workspace.querySelectorAll("[data-rmc-django-view-toggle] [data-rmc-django-view]").forEach(function (btn) {
      var active = btn.getAttribute("data-rmc-django-view") === mode;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });

    workspace.querySelectorAll("[data-rmc-django-mode-panel]").forEach(function (panel) {
      var panelMode = panel.getAttribute("data-rmc-django-mode-panel");
      var show = panelMode === mode;
      if (show) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    });

    closePreviewDrawer();
  }

  function initViewToggle() {
    var workspace = document.querySelector('[data-rmc-django-workspace="change-form"]');
    if (!workspace) return;

    var stored = null;
    try {
      stored = sessionStorage.getItem(VIEW_KEY);
    } catch (_e) {
      stored = null;
    }
    if (stored === "preview") stored = "form";
    if (stored === "form" || stored === "audit") {
      setViewMode(workspace, stored);
    } else {
      setViewMode(workspace, "form");
    }

    workspace.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-rmc-django-view-toggle] [data-rmc-django-view]");
      if (!btn) return;
      ev.preventDefault();
      var mode = btn.getAttribute("data-rmc-django-view");
      setViewMode(workspace, mode);
    });
  }

  function initPreviewOpeners() {
    // Keep close handlers for model-specific real drawers (e.g. CountryRegistry).
    // Do not create staged Django preview drawers from generic chrome.
    document.addEventListener("click", function (ev) {
      var closeBtn = ev.target.closest("[data-rmc-django-preview-close], [data-rmc-mv-preview-close]");
      if (closeBtn) {
        ev.preventDefault();
        closePreviewDrawer(closeBtn.closest(".rmc-mv-preview-drawer"));
      }
    });
  }

  function initChangelistRail() {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-rmc-changelist-open-filters]");
      if (!btn) return;
      ev.preventDefault();
      var trigger = document.querySelector("[data-rmc-changelist-filter-trigger]");
      if (trigger) trigger.click();
    });
  }

  function initOnThisPage() {
    var nav = document.querySelector("[data-rmc-onthispage]");
    var main = document.getElementById("content-main");
    if (!nav || !main) return;

    var sections = main.querySelectorAll("fieldset.module, .inline-group");
    var items = [];

    Array.prototype.forEach.call(sections, function (sec, i) {
      if (sec.offsetParent === null && sec.getClientRects().length === 0) return;
      var label = sectionLabel(sec, items.length);
      if (!sec.id) sec.id = "rmc-sec-" + (i + 1);
      sec.style.scrollMarginTop = "84px";

      var a = document.createElement("a");
      a.href = "#" + sec.id;
      var num = document.createElement("span");
      num.className = "num";
      num.textContent = String(items.length + 1);
      var lbl = document.createElement("span");
      lbl.className = "lbl";
      lbl.textContent = label;
      a.appendChild(num);
      a.appendChild(lbl);
      nav.appendChild(a);
      items.push({ a: a, sec: sec });
    });

    if (!items.length) {
      var card = nav.closest(".rmc-rail-card");
      if (card) card.style.display = "none";
      return;
    }

    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (e) {
            if (e.isIntersecting) {
              items.forEach(function (it) {
                it.a.classList.toggle("is-active", it.sec === e.target);
              });
            }
          });
        },
        { rootMargin: "-35% 0px -55% 0px" }
      );
      items.forEach(function (it) {
        io.observe(it.sec);
      });
    }
  }

  function initPageAwarePulse() {
    var pulse = document.querySelector("[data-rmc-django-rail-pulse]");
    if (!pulse) return;
    var main = document.getElementById("content-main");
    var form =
      (main && main.querySelector("form")) ||
      document.querySelector(".rmc-django-form-panel form") ||
      document.querySelector("#content-main form");
    if (!form) return;

    var elSections = pulse.querySelector('[data-rmc-pulse="sections"]');
    var elRequired = pulse.querySelector('[data-rmc-pulse="required-empty"]');
    var elDirty = pulse.querySelector('[data-rmc-pulse="dirty"]');
    var cleanLabel = pulse.getAttribute("data-rmc-pulse-clean") || "Clean";
    var dirtyLabel = pulse.getAttribute("data-rmc-pulse-dirty") || "Unsaved";
    var dirty = false;

    function countSections() {
      if (!main) return 0;
      return main.querySelectorAll("fieldset.module, .inline-group").length;
    }

    function countRequiredEmpty() {
      var nodes = form.querySelectorAll(
        "input[required], select[required], textarea[required], .required input, .required select, .required textarea"
      );
      var empty = 0;
      Array.prototype.forEach.call(nodes, function (el) {
        if (el.disabled || el.type === "hidden") return;
        var val = (el.value || "").trim();
        if (!val) empty += 1;
      });
      return empty;
    }

    function refresh() {
      if (elSections) elSections.textContent = String(countSections());
      if (elRequired) elRequired.textContent = String(countRequiredEmpty());
      if (elDirty) {
        elDirty.textContent = dirty ? dirtyLabel : cleanLabel;
        elDirty.classList.toggle("is-warn", dirty);
      }
    }

    form.addEventListener("input", function () {
      dirty = true;
      refresh();
    });
    form.addEventListener("change", function () {
      dirty = true;
      refresh();
    });
    refresh();
  }

  ready(function () {
    initOnThisPage();
    initViewToggle();
    initPreviewOpeners();
    initChangelistRail();
    initPageAwarePulse();
  });
})();
