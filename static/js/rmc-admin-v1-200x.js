/**
 * Manager /admin/ v1 200x — catalog tabs + search (preview parity).
 * v3.62.13 (2026-05-22)
 */
(function () {
  "use strict";

  function initCatalogTabs() {
    var root = document.querySelector("[data-rmc-admin-catalog-index]");
    if (!root) return;
    var tabs = root.querySelectorAll(".cp-tab[data-rmc-catalog-tab]");
    var cards = root.querySelectorAll("[data-rmc-catalog-card]");
    if (!tabs.length) return;

    function activateTab(tab) {
      tabs.forEach(function (t) {
        t.removeAttribute("data-active");
        t.setAttribute("aria-selected", "false");
      });
      tab.setAttribute("data-active", "");
      tab.setAttribute("aria-selected", "true");
      var sectionId = tab.getAttribute("data-rmc-catalog-tab") || "";
      cards.forEach(function (card) {
        if (!sectionId || sectionId === "overview") {
          card.hidden = false;
          return;
        }
        card.hidden = card.getAttribute("data-rmc-catalog-section-id") !== sectionId;
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateTab(tab);
      });
      tab.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          activateTab(tab);
        }
      });
    });
  }

  function initCatalogSearch() {
    var root = document.querySelector("[data-rmc-admin-catalog-index]");
    if (!root) return;
    var input = root.querySelector("[data-rmc-admin-catalog-search]");
    var cards = root.querySelectorAll("[data-rmc-catalog-card]");
    var empty = root.querySelector("[data-rmc-admin-catalog-empty]");
    if (!input || !cards.length) return;

    function apply(query) {
      var q = (query || "").toLowerCase().trim();
      var visible = 0;
      cards.forEach(function (card) {
        var blob = card.getAttribute("data-admin-search") || "";
        var match = !q || blob.indexOf(q) !== -1;
        card.hidden = !match;
        if (match) visible += 1;
      });
      if (empty) empty.hidden = visible > 0;
    }

    var debounce = null;
    input.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        apply(input.value);
      }, 120);
    });
  }

  function initSurfacePreviewChangeform(root) {
    var tabs = root.querySelectorAll("[data-cp-form-tab]");
    var panels = root.querySelectorAll("[data-cp-form-panel]");
    if (!tabs.length || !panels.length) return;

    function activateTab(tab) {
      var panelId = tab.getAttribute("data-cp-form-tab") || "";
      tabs.forEach(function (t) {
        t.removeAttribute("data-active");
        t.setAttribute("aria-selected", "false");
      });
      tab.setAttribute("data-active", "");
      tab.setAttribute("aria-selected", "true");
      panels.forEach(function (panel) {
        var match = panel.getAttribute("data-cp-form-panel") === panelId;
        if (match) {
          panel.removeAttribute("hidden");
          panel.setAttribute("data-active", "");
        } else {
          panel.setAttribute("hidden", "");
          panel.removeAttribute("data-active");
        }
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateTab(tab);
      });
    });

    var saveBtn = root.querySelector("[data-rmc-preview-save]");
    var status = root.querySelector("[data-rmc-preview-status]");
    if (saveBtn && status) {
      saveBtn.addEventListener("click", function () {
        status.classList.remove("visually-hidden");
        status.textContent =
          "Preview sandbox — edits are not persisted. Open a school from the changelist to save.";
      });
    }
  }

  function initSurfacePreviewChangelist(root) {
    root.querySelectorAll("[data-cp-filter-group]").forEach(function (group) {
      var pills = group.querySelectorAll("[data-cp-filter-pill]");
      pills.forEach(function (pill) {
        pill.addEventListener("click", function () {
          pills.forEach(function (p) {
            p.removeAttribute("data-active");
          });
          pill.setAttribute("data-active", "");
        });
      });
    });

    var pager = root.querySelector("[data-cp-pager-preview]");
    if (!pager) return;
    var pagePills = pager.querySelectorAll("[data-cp-pager-pill]");
    pagePills.forEach(function (pill) {
      pill.addEventListener("click", function () {
        pagePills.forEach(function (p) {
          p.removeAttribute("data-active");
        });
        pill.setAttribute("data-active", "");
      });
    });
  }

  function initSurfacePreviews() {
    document
      .querySelectorAll('[data-rmc-surface-preview-interactive="changeform"]')
      .forEach(initSurfacePreviewChangeform);
    document
      .querySelectorAll('[data-rmc-surface-preview-interactive="changelist"]')
      .forEach(initSurfacePreviewChangelist);
  }

  function initCatalogExpandLinks() {
    document.querySelectorAll("[data-rmc-catalog-expand-details]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        var targetId = link.getAttribute("data-rmc-catalog-expand-details");
        if (!targetId) return;
        var details = document.getElementById(targetId);
        if (!details || details.tagName !== "DETAILS") return;
        event.preventDefault();
        details.open = true;
        details.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function boot() {
    if (!document.body || !document.body.classList.contains("admin-manager-shell")) {
      return;
    }
    initCatalogTabs();
    initCatalogSearch();
    initCatalogExpandLinks();
    initSurfacePreviews();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
