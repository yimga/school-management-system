/**
 * Platform /admin/ model catalog — filter sidebar + index by search string.
 * unbounded-collection-allow: admin-catalog-bounded-django-model-registry
 */
(function () {
  "use strict";

  function norm(value) {
    return (value || "").toLowerCase().trim();
  }

  function initSearch(input, getRows, onFilter) {
    if (!input) return;
    var debounce = null;
    input.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        onFilter(norm(input.value));
      }, 120);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        input.value = "";
        onFilter("");
        input.blur();
      }
    });
  }

  function filterRows(rows, query) {
    rows.forEach(function (row) {
      var blob = row.getAttribute("data-admin-search") || "";
      var match = !query || blob.indexOf(query) !== -1;
      row.hidden = !match;
      row.classList.toggle("rmc-admin-catalog-row--hidden", !match);
    });
  }

  function filterSections(sections, query) {
    sections.forEach(function (section) {
      var rows = section.querySelectorAll("[data-admin-search]");
      var visible = 0;
      rows.forEach(function (row) {
        var blob = row.getAttribute("data-admin-search") || "";
        var match = !query || blob.indexOf(query) !== -1;
        row.hidden = !match;
        visible += match ? 1 : 0;
      });
      section.hidden = query && visible === 0;
      var countEl = section.querySelector("[data-rmc-section-visible-count]");
      if (countEl) {
        countEl.textContent = String(visible);
      }
    });
  }

  function initIndex() {
    var root = document.querySelector("[data-rmc-admin-catalog-index]");
    if (!root) return;
    var input = root.querySelector("[data-rmc-admin-catalog-search]");
    var sections = root.querySelectorAll("[data-rmc-admin-catalog-section]");
    initSearch(input, function () {
      return root.querySelectorAll("[data-admin-search]");
    }, function (query) {
      filterSections(sections, query);
      var empty = root.querySelector("[data-rmc-admin-catalog-empty]");
      if (empty) {
        var anyVisible = Array.prototype.some.call(
          root.querySelectorAll("[data-admin-search]"),
          function (row) {
            return !row.hidden;
          }
        );
        empty.hidden = anyVisible;
      }
    });
  }

  function initSidebar() {
    var tree = document.querySelector("[data-rmc-platform-admin-app-tree]");
    if (!tree) return;
    var input = document.querySelector("[data-rmc-sidebar-catalog-search]");
    var rows = tree.querySelectorAll("[data-admin-search]");
    initSearch(input, function () {
      return rows;
    }, function (query) {
      filterRows(rows, query);
      tree.querySelectorAll(".admin-sidebar-app-group").forEach(function (group) {
        var modelRows = group.querySelectorAll(
          ".admin-sidebar-model-link[data-admin-search]"
        );
        var appTitle = group.querySelector(".admin-sidebar-app-title");
        var visible = 0;
        modelRows.forEach(function (row) {
          if (!row.hidden) visible += 1;
        });
        if (query) {
          group.hidden = visible === 0;
          if (appTitle && visible > 0) {
            var openBtn = group.querySelector(".admin-sidebar-app-toggle");
            if (openBtn && group.__x) {
              /* alpine may control x-show — force open via click if collapsed */
            }
            var list = group.querySelector(".admin-sidebar-model-list");
            if (list) list.style.display = "";
          }
        } else {
          group.hidden = false;
        }
      });
      var empty = document.querySelector("[data-rmc-sidebar-catalog-empty]");
      if (empty) {
        var anyVisible = Array.prototype.some.call(rows, function (row) {
          return !row.hidden;
        });
        empty.hidden = anyVisible || !query;
      }
    });
  }

  function boot() {
    initIndex();
    initSidebar();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
