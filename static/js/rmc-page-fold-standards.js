/**
 * Page fold standards - measure content depth, enforce 2-fold back-to-top threshold,
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
    if (window.RMCBackToTop && window.RMCBackToTop.refresh) {
      window.RMCBackToTop.refresh();
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

  function sectionNavDisabled(root) {
    var node = root;
    while (node && node !== document.documentElement) {
      if (node.getAttribute && node.getAttribute("data-rmc-section-nav") === "off") {
        return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  function sectionNavLabelFor(el) {
    var explicit = el.getAttribute("data-rmc-section-nav-label");
    if (explicit) {
      return explicit.trim().slice(0, 48);
    }
    var labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      var ref = document.getElementById(labelledBy);
      if (ref && ref.textContent) {
        return ref.textContent.trim().replace(/\s+/g, " ").slice(0, 48);
      }
    }
    var heading = el.querySelector("h2, h3, [role='heading']");
    if (heading && heading.textContent) {
      return heading.textContent.trim().replace(/\s+/g, " ").slice(0, 48);
    }
    return (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 48);
  }

  function initAutoSectionNav() {
    var roots = document.querySelectorAll(
      '[data-rmc-section-nav="auto"], [data-rmc-page-fold-nav="required"], [data-rmc-cp-page-body="1"], #cp-main-content.cp-page-body, .cp-admin-page-body'
    );
    if (!roots.length) return;
    if (document.querySelector("[data-feature-cat-tabs]")) return;
    if (document.querySelector(".rmc-section-nav[data-rmc-auto-section-nav]")) {
      return;
    }
    if (
      document.querySelector("nav.rmc-section-nav:not([data-rmc-auto-section-nav])") ||
      document.querySelector("nav.cp-section-nav") ||
      document.querySelector(".cp-hero__actions--toolbar.rmc-section-nav")
    ) {
      return;
    }

    var root = roots[0];
    if (sectionNavDisabled(root)) return;
    if (root.querySelector('[data-rmc-section-nav="off"]')) return;
    if (
      document.querySelector("[data-rmc-section-nav-curated]") ||
      root.closest('[data-rmc-section-nav="curated"]')
    ) {
      return;
    }

    var autoMode =
      root.getAttribute("data-rmc-section-nav") === "auto" ||
      !!root.closest('[data-rmc-section-nav="auto"]');

    var headings = root.querySelectorAll(
      autoMode
        ? "h2[id], h3[id], [data-rmc-section-anchor]"
        : "[data-rmc-section-anchor]"
    );
    if (headings.length < 2) return;

    var items = [];
    var seenIds = {};
    headings.forEach(function (el) {
      if (el.closest("[data-rmc-section-nav-skip]")) return;
      var id = el.id;
      if (!id) {
        id = slugifyId(sectionNavLabelFor(el));
        if (!id || document.getElementById(id) || seenIds[id]) return;
        el.id = id;
      }
      if (seenIds[id]) return;
      seenIds[id] = true;
      if (!el.hasAttribute("data-rmc-section-anchor")) {
        el.setAttribute("data-rmc-section-anchor", "1");
      }
      var label = sectionNavLabelFor(el);
      if (!label) return;
      items.push({ id: id, label: label });
    });
    if (items.length < 2) return;

    var nav = document.createElement("nav");
    nav.className = "rmc-section-nav rmc-section-nav--inline mb-2";
    nav.setAttribute("aria-label", "On this page");
    nav.setAttribute("data-rmc-auto-section-nav", "1");

    var label = document.createElement("span");
    label.className = "rmc-section-nav__inline-label";
    label.textContent = "Jump to";

    var subnav = document.createElement("div");
    subnav.className = "rmc-surface-subnav";
    subnav.setAttribute("role", "list");
    items.forEach(function (item, idx) {
      var a = document.createElement("a");
      a.href = "#" + item.id;
      a.textContent = item.label;
      a.className = "rmc-section-nav__link";
      a.setAttribute("role", "listitem");
      a.setAttribute("data-rmc-section-anchor", "1");
      if (idx === 0) {
        a.classList.add("is-active");
        a.classList.add("active");
      }
      subnav.appendChild(a);
    });
    nav.appendChild(label);
    nav.appendChild(subnav);

    var mount =
      root.querySelector(".card-body") ||
      root.querySelector(".cp-page-body") ||
      root;
    mount.insertBefore(nav, mount.firstChild);
  }

  var CARD_PAGE_SIZE = 6;
  var STAGES_STORAGE = "rmcFoldStages:v1:";

  function readStagePref(key) {
    if (!key) return null;
    try {
      return localStorage.getItem(STAGES_STORAGE + key);
    } catch (_) {
      return null;
    }
  }
  function writeStagePref(key, value) {
    if (!key) return;
    try {
      localStorage.setItem(STAGES_STORAGE + key, value);
    } catch (_) {}
  }

  function buildStagesNav(items, activeId, onSelect) {
    var nav = document.createElement("div");
    nav.className = "rmc-fold-stages";
    nav.setAttribute("role", "tablist");
    nav.setAttribute("aria-label", "Page sections");
    nav.setAttribute("data-rmc-page-fold-nav", "required");

    items.forEach(function (item) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "rmc-fold-stages__btn";
      btn.setAttribute("role", "tab");
      btn.setAttribute("data-rmc-fold-stage-btn", item.id);
      btn.textContent = item.label;
      btn.setAttribute("aria-pressed", item.id === activeId ? "true" : "false");
      btn.addEventListener("click", function () {
        onSelect(item.id);
      });
      nav.appendChild(btn);
    });

    var hint = document.createElement("span");
    hint.className = "rmc-fold-stages__hint";
    hint.textContent = "One section at a time";
    nav.appendChild(hint);
    return nav;
  }

  function syncStageButtons(nav, activeId) {
    nav.querySelectorAll("[data-rmc-fold-stage-btn]").forEach(function (btn) {
      var on = btn.getAttribute("data-rmc-fold-stage-btn") === activeId;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  /** Explicit fold stages: [data-rmc-fold-stages] > [data-rmc-fold-stage] */
  function initFoldStages(root) {
    var scope = root || document;
    var hosts = scope.querySelectorAll("[data-rmc-fold-stages]");
    hosts.forEach(function (host) {
      if (host.getAttribute("data-rmc-fold-stages-ready") === "1") return;
      var stages = Array.prototype.filter.call(host.children, function (el) {
        return el.nodeType === 1 && el.hasAttribute("data-rmc-fold-stage");
      });
      if (stages.length < 2) return;
      host.setAttribute("data-rmc-fold-stages-ready", "1");

      var persistKey = host.getAttribute("data-rmc-fold-stages-persist") || "";
      var items = stages.map(function (el, idx) {
        var id =
          el.getAttribute("data-rmc-fold-stage") ||
          el.id ||
          "stage-" + (idx + 1);
        el.setAttribute("data-rmc-fold-stage", id);
        if (!el.id) el.id = "rmc-fold-" + id;
        var label =
          el.getAttribute("data-rmc-fold-stage-label") ||
          sectionNavLabelFor(el) ||
          id;
        return { id: id, label: label, el: el };
      });

      var preferred = readStagePref(persistKey);
      var initial = items[0].id;
      if (preferred && items.some(function (i) { return i.id === preferred; })) {
        initial = preferred;
      } else {
        var def = items.find(function (i) {
          return i.el.getAttribute("data-rmc-fold-stage-default") === "1";
        });
        if (def) initial = def.id;
      }

      function show(id) {
        items.forEach(function (item) {
          var on = item.id === id;
          item.el.hidden = !on;
          if (on) {
            item.el.removeAttribute("hidden");
          } else {
            item.el.setAttribute("hidden", "hidden");
          }
        });
        syncStageButtons(nav, id);
        writeStagePref(persistKey, id);
        applyFoldAttributes();
        try {
          window.scrollTo({ top: Math.max(0, host.getBoundingClientRect().top + window.scrollY - 80), behavior: "smooth" });
        } catch (_) {}
      }

      var nav = buildStagesNav(items, initial, show);
      host.insertBefore(nav, host.firstChild);
      show(initial);

      // Deep-link: #rollout / #rmc-fold-rollout / hash matching stage id
      function applyHash() {
        var hash = (location.hash || "").replace(/^#/, "");
        if (!hash) return;
        var match = items.find(function (i) {
          return i.id === hash || i.el.id === hash || hash.indexOf(i.id) !== -1;
        });
        if (match) show(match.id);
      }
      applyHash();
      window.addEventListener("hashchange", applyHash);
    });
  }

  /**
   * Fieldset accordion - turns a mega-form into fold stages (one group visible).
   * Host: form[data-rmc-fieldset-accordion="1"]. Id'd fieldsets = stages;
   * id-less fieldsets share a "Content blocks" stage (paginated).
   */
  function initFieldsetAccordion(root) {
    var scope = root || document;
    var hosts = scope.querySelectorAll('[data-rmc-fieldset-accordion="1"]');
    hosts.forEach(function (host) {
      if (host.getAttribute("data-rmc-fieldset-accordion-ready") === "1") return;
      var fieldsets = Array.prototype.slice.call(host.querySelectorAll("fieldset")).filter(function (fs) {
        return !fs.closest("[data-rmc-fieldset-accordion-skip]");
      });
      if (fieldsets.length < 2) return;
      host.setAttribute("data-rmc-fieldset-accordion-ready", "1");

      var groups = [];
      var orphans = [];
      fieldsets.forEach(function (fs) {
        var legend = fs.querySelector("legend");
        var label = legend
          ? legend.textContent.trim().replace(/\s+/g, " ").slice(0, 40)
          : "Section";
        if (fs.id) {
          groups.push({ id: fs.id, label: label, nodes: [fs] });
        } else {
          orphans.push(fs);
        }
      });
      if (orphans.length) {
        groups.push({
          id: "rmc-fieldset-more",
          label: "Content blocks",
          nodes: orphans,
          paginate: true,
        });
      }
      if (groups.length < 2) return;

      var contentHeading = host.querySelector("#cockpit-content-blocks, [data-rmc-fieldset-more-heading]");
      var persistKey =
        host.getAttribute("data-rmc-fieldset-accordion-persist") ||
        "fieldset:" + (host.id || location.pathname);
      var preferred = readStagePref(persistKey);
      var initial = groups[0].id;
      if (preferred && groups.some(function (g) { return g.id === preferred; })) {
        initial = preferred;
      }

      function show(id) {
        groups.forEach(function (g) {
          var on = g.id === id;
          g.nodes.forEach(function (node) {
            if (on) {
              node.hidden = false;
              node.removeAttribute("hidden");
              node.classList.remove("d-none");
            } else {
              node.hidden = true;
              node.setAttribute("hidden", "hidden");
            }
          });
        });
        if (contentHeading) {
          var showMore = id === "rmc-fieldset-more";
          contentHeading.hidden = !showMore;
          if (showMore) contentHeading.removeAttribute("hidden");
          else contentHeading.setAttribute("hidden", "hidden");
        }
        syncStageButtons(nav, id);
        writeStagePref(persistKey, id);
        applyFoldAttributes();
      }

      var nav = buildStagesNav(
        groups.map(function (g) { return { id: g.id, label: g.label }; }),
        initial,
        show
      );
      host.insertBefore(nav, host.firstChild);
      show(initial);

      var contentGroup = groups.find(function (g) { return g.paginate; });
      if (contentGroup && contentGroup.nodes.length > CARD_PAGE_SIZE) {
        paginateNodeList(contentGroup.nodes, CARD_PAGE_SIZE, contentGroup.nodes[0].parentNode);
      }
    });
  }

  function paginateNodeList(nodes, pageSize, insertHost) {
    if (!nodes || nodes.length <= pageSize || !insertHost) return;
    if (insertHost.getAttribute("data-rmc-card-pager-ready") === "1") return;
    insertHost.setAttribute("data-rmc-card-pager-ready", "1");
    var totalPages = Math.ceil(nodes.length / pageSize);
    var nav = buildTaskPager("Section pages", totalPages, function (p) {
      nodes.forEach(function (node, idx) {
        var pageIdx = Math.floor(idx / pageSize) + 1;
        var hide = pageIdx !== p;
        // Respect parent stage visibility: only toggle d-none when parent stage is visible
        if (node.hidden && node.hasAttribute("hidden")) return;
        node.classList.toggle("d-none", hide);
      });
    });
    nav.classList.add("rmc-card-pager");
    var last = nodes[nodes.length - 1];
    if (last && last.parentNode) {
      last.parentNode.insertBefore(nav, last.nextSibling);
    }
  }

  /** Card / section stack pager for [data-rmc-paginate-cards] */
  function initCardStackPagination(root) {
    var scope = root || document;
    var hosts = scope.querySelectorAll("[data-rmc-paginate-cards]");
    hosts.forEach(function (host) {
      if (host.getAttribute("data-rmc-card-pager-ready") === "1") return;
      var sel = host.getAttribute("data-rmc-paginate-cards") || ":scope > *";
      var cards;
      try {
        cards = Array.prototype.slice.call(host.querySelectorAll(sel));
      } catch (_) {
        cards = Array.prototype.slice.call(host.children);
      }
      cards = cards.filter(function (el) {
        return el.nodeType === 1 && !el.classList.contains("rmc-fold-stages") && !el.classList.contains("rmc-task-pager") && !el.classList.contains("rmc-card-pager");
      });
      var size = parseInt(host.getAttribute("data-rmc-paginate-size") || String(CARD_PAGE_SIZE), 10) || CARD_PAGE_SIZE;
      if (cards.length <= size) return;
      paginateNodeList(cards, size, host);
    });
  }

  /** Progressive disclosure: collapse [data-rmc-secondary-fold] into details */
  function initSecondaryFolds(root) {
    var scope = root || document;
    var nodes = scope.querySelectorAll("[data-rmc-secondary-fold]");
    nodes.forEach(function (el) {
      if (el.getAttribute("data-rmc-secondary-fold-ready") === "1") return;
      if (el.tagName === "DETAILS" || el.classList.contains("rmc-collapsable")) {
        el.setAttribute("data-rmc-secondary-fold-ready", "1");
        return;
      }
      el.setAttribute("data-rmc-secondary-fold-ready", "1");
      var title =
        el.getAttribute("data-rmc-secondary-fold") ||
        el.getAttribute("data-rmc-fold-stage-label") ||
        sectionNavLabelFor(el) ||
        "More details";
      var key = el.getAttribute("data-rmc-collapsable-key") || el.id || "";
      var details = document.createElement("details");
      details.className = "rmc-collapsable";
      details.setAttribute("data-rmc-collapsable-default", "collapsed");
      if (key) details.setAttribute("data-rmc-collapsable-key", key);
      details.setAttribute("data-rmc-collapsable-chrome", "section");
      var summary = document.createElement("summary");
      summary.className = "rmc-collapsable__head";
      var t = document.createElement("span");
      t.className = "rmc-collapsable__title";
      t.textContent = title;
      var chev = document.createElement("span");
      chev.className = "rmc-collapsable__chevron";
      chev.setAttribute("aria-hidden", "true");
      chev.textContent = "v";
      summary.appendChild(t);
      summary.appendChild(chev);
      var body = document.createElement("div");
      body.className = "rmc-collapsable__body";
      var parent = el.parentNode;
      if (!parent) return;
      parent.insertBefore(details, el);
      details.appendChild(summary);
      details.appendChild(body);
      body.appendChild(el);
    });
  }

  function init() {
    applyFoldAttributes();
    initTaskListPagination(document);
    initTableClientPagination(document);
    initFoldStages(document);
    initFieldsetAccordion(document);
    initCardStackPagination(document);
    initSecondaryFolds(document);
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

  window.RMCPageFold = {
    refresh: function () {
      applyFoldAttributes();
      initTaskListPagination(document);
      initTableClientPagination(document);
      initFoldStages(document);
      initFieldsetAccordion(document);
      initCardStackPagination(document);
      initSecondaryFolds(document);
    },
  };
})();
