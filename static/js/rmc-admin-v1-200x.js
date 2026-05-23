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

  function boot() {
    if (!document.body || !document.body.classList.contains("admin-manager-shell")) {
      return;
    }
    initCatalogTabs();
    initCatalogSearch();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
