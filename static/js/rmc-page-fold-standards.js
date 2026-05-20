/**
 * Page fold standards — measure content depth, enforce 2-fold back-to-top threshold,
 * client pagination for task lists/tables marked data-rmc-scroll-policy="paginate".
 */
(function () {
  "use strict";

  var TASK_PAGE_SIZE = 20;
  var TABLE_PAGE_SIZE = 25;

  function foldHeight() {
    return window.RMC && window.RMC.getFoldHeight
      ? window.RMC.getFoldHeight()
      : Math.max(window.innerHeight || 0, 320);
  }

  function measureFoldCount() {
    var doc = document.documentElement;
    var height = Math.max(
      doc.scrollHeight,
      document.body ? document.body.scrollHeight : 0
    );
    return height / foldHeight();
  }

  function applyFoldAttributes() {
    var folds = measureFoldCount();
    var html = document.documentElement;
    html.setAttribute("data-rmc-measured-folds", folds.toFixed(2));
    if (folds >= 2) {
      html.setAttribute("data-rmc-exceeds-2-folds", "1");
    } else {
      html.removeAttribute("data-rmc-exceeds-2-folds");
    }
    if (folds > 4) {
      html.setAttribute("data-rmc-exceeds-4-folds", "1");
      if (typeof console !== "undefined" && console.warn) {
        console.warn(
          "[rmc-page-fold] Content exceeds 4 viewport folds (" +
            folds.toFixed(1) +
            "). Refactor with tabs or pagination."
        );
      }
    } else {
      html.removeAttribute("data-rmc-exceeds-4-folds");
    }
  }

  function buildTaskPager(ariaLabel, totalPages, renderPage) {
    var nav = document.createElement("nav");
    nav.className =
      "rmc-task-pager d-flex flex-wrap align-items-center justify-content-between gap-2 mt-2";
    nav.setAttribute("aria-label", ariaLabel);
    nav.setAttribute("data-rmc-task-pager", "1");

    var info = document.createElement("span");
    info.className = "small text-muted";
    var prev = document.createElement("button");
    prev.type = "button";
    prev.className = "btn btn-outline-secondary btn-sm";
    prev.textContent = "Previous";
    var next = document.createElement("button");
    next.type = "button";
    next.className = "btn btn-outline-secondary btn-sm";
    next.textContent = "Next";

    var page = 1;

    function render() {
      renderPage(page);
      info.textContent = "Page " + page + " of " + totalPages;
      prev.disabled = page <= 1;
      next.disabled = page >= totalPages;
    }

    prev.addEventListener("click", function () {
      if (page > 1) {
        page -= 1;
        render();
      }
    });
    next.addEventListener("click", function () {
      if (page < totalPages) {
        page += 1;
        render();
      }
    });

    nav.appendChild(prev);
    nav.appendChild(info);
    nav.appendChild(next);
    render();
    return nav;
  }

  function initTaskListPagination(root) {
    var scope = root || document;
    var lists = scope.querySelectorAll(
      '[data-rmc-scroll-policy="paginate"] .feature-category-card ul, ' +
        '[data-rmc-scroll-policy="paginate"] [data-rmc-paginate-list="1"]'
    );
    lists.forEach(function (ul) {
      if (ul.getAttribute("data-rmc-pager-ready") === "1") return;
      var rows = Array.prototype.filter.call(ul.children, function (node) {
        return (
          node.nodeType === 1 &&
          node.classList &&
          node.classList.contains("feature-toggle-row")
        );
      });
      if (rows.length <= TASK_PAGE_SIZE) return;

      ul.setAttribute("data-rmc-pager-ready", "1");
      var totalPages = Math.ceil(rows.length / TASK_PAGE_SIZE);
      var nav = buildTaskPager("Feature list pages", totalPages, function (p) {
        rows.forEach(function (row, idx) {
          var pageIdx = Math.floor(idx / TASK_PAGE_SIZE) + 1;
          row.classList.toggle("d-none", pageIdx !== p);
        });
      });
      ul.parentNode.insertBefore(nav, ul.nextSibling);
    });
  }

  function initTableClientPagination(root) {
    var scope = root || document;
    var tables = scope.querySelectorAll(
      '[data-rmc-scroll-policy="paginate"] table tbody'
    );
    tables.forEach(function (tbody) {
      if (tbody.getAttribute("data-rmc-pager-ready") === "1") return;
      var rows = Array.prototype.filter.call(tbody.children, function (tr) {
        return tr.nodeType === 1 && tr.tagName === "TR";
      });
      if (rows.length <= TABLE_PAGE_SIZE) return;
      tbody.setAttribute("data-rmc-pager-ready", "1");
      var table = tbody.closest("table");
      var wrap = table ? table.closest(".table-responsive") : null;
      var host = wrap || table;
      if (!host) return;

      var totalPages = Math.ceil(rows.length / TABLE_PAGE_SIZE);
      var nav = buildTaskPager("Table pages", totalPages, function (p) {
        rows.forEach(function (row, idx) {
          var pageIdx = Math.floor(idx / TABLE_PAGE_SIZE) + 1;
          row.classList.toggle("d-none", pageIdx !== p);
        });
      });
      host.parentNode.insertBefore(nav, host.nextSibling);
    });
  }

  function slugifyId(text) {
    return (
      "section-" +
      String(text || "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 48)
    );
  }

  function initAutoSectionNav() {
    var roots = document.querySelectorAll('[data-rmc-page-fold-nav="required"]');
    if (!roots.length) return;
    if (document.querySelector("[data-feature-cat-tabs]")) return;
    if (document.querySelector(".rmc-section-nav[data-rmc-auto-section-nav]")) {
      return;
    }
    if (document.querySelector("nav.rmc-section-nav:not([data-rmc-auto-section-nav])")) {
      return;
    }

    var root = roots[0];
    var headings = root.querySelectorAll(
      "h2[id], h3[id], [data-rmc-section-anchor]"
    );
    if (headings.length < 2) return;

    var items = [];
    headings.forEach(function (el) {
      var id = el.id;
      if (!id) {
        id = slugifyId(el.textContent);
        if (!id || document.getElementById(id)) return;
        el.id = id;
      }
      if (!el.hasAttribute("data-rmc-section-anchor")) {
        el.setAttribute("data-rmc-section-anchor", "1");
      }
      var label = (el.textContent || "").trim().slice(0, 48);
      if (!label) return;
      items.push({ id: id, label: label });
    });
    if (items.length < 2) return;

    var nav = document.createElement("nav");
    nav.className =
      "rmc-section-nav rmc-page-fold-nav--sticky rmc-section-nav--horizontal rmc-horizontal-nav-rail mb-3";
    nav.setAttribute("aria-label", "Page sections");
    nav.setAttribute("data-rmc-auto-section-nav", "1");

    var list = document.createElement("ul");
    list.className = "rmc-section-nav__list";
    items.forEach(function (item, idx) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = "#" + item.id;
      a.textContent = item.label;
      if (idx === 0) a.classList.add("is-active");
      li.appendChild(a);
      list.appendChild(li);
    });
    nav.appendChild(list);

    var mount =
      root.querySelector(".card-body") ||
      root.querySelector(".cp-page-body") ||
      root;
    mount.insertBefore(nav, mount.firstChild);
  }

  function init() {
    applyFoldAttributes();
    initTaskListPagination(document);
    initTableClientPagination(document);
    initAutoSectionNav();
    window.addEventListener(
      "resize",
      function () {
        applyFoldAttributes();
      },
      { passive: true }
    );
    window.setTimeout(applyFoldAttributes, 400);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
