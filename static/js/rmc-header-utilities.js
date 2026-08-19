/**
 * Quiet-header Utilities: searchable tiles, recents, focus trap, Copilot,
 * and Tools-rail Help panel (Ask Copilot / walkthrough / support).
 */
(function () {
  "use strict";

  var RECENTS_KEY = "rmc.headerUtilities.recents.v1";
  var RECENTS_MAX = 4;

  function storageKey(root) {
    var surface = (root && root.getAttribute("data-rmc-header-utilities-root")) || "tenant";
    return RECENTS_KEY + "." + surface;
  }

  function readRecents(root) {
    try {
      var raw = window.localStorage.getItem(storageKey(root));
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (_err) {
      return [];
    }
  }

  function writeRecents(root, keys) {
    try {
      window.localStorage.setItem(storageKey(root), JSON.stringify(keys.slice(0, RECENTS_MAX)));
    } catch (_err) {}
  }

  function recordRecent(root, key) {
    if (!key) return;
    var next = [key].concat(readRecents(root).filter(function (item) { return item !== key; }));
    writeRecents(root, next);
  }

  function tileLabel(el) {
    return (el.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function applyFilter(root, query) {
    var q = (query || "").trim().toLowerCase();
    var items = root.querySelectorAll("[data-rmc-util-key]");
    items.forEach(function (el) {
      if (el.closest("[data-rmc-util-recents-grid]")) return;
      el.hidden = Boolean(q) && tileLabel(el).indexOf(q) === -1;
    });
  }

  function renderRecents(root) {
    var section = root.querySelector("[data-rmc-util-recents]");
    var grid = root.querySelector("[data-rmc-util-recents-grid]");
    if (!section || !grid) return;
    grid.innerHTML = "";
    var keys = readRecents(root);
    keys.forEach(function (key) {
      var source = null;
      root.querySelectorAll("[data-rmc-util-key]").forEach(function (el) {
        if (source) return;
        if (el.getAttribute("data-rmc-util-key") !== key) return;
        if (el.closest("[data-rmc-util-recents-grid]")) return;
        source = el;
      });
      if (!source) return;
      var clone = source.cloneNode(true);
      clone.setAttribute("data-rmc-util-recent-clone", "1");
      grid.appendChild(clone);
    });
    section.hidden = grid.childElementCount === 0;
  }

  function focusables(menu) {
    return Array.prototype.slice.call(
      menu.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter(function (el) {
      return !el.hidden && el.offsetParent !== null;
    });
  }

  function trapTab(event, menu) {
    if (event.key !== "Tab") return;
    var nodes = focusables(menu);
    if (!nodes.length) return;
    var first = nodes[0];
    var last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function openCopilot() {
    var toggle = document.querySelector("[data-rmc-copilot-toggle]");
    var shell = document.querySelector(".rmc-app-shell");
    if (toggle) toggle.click();
    else if (shell) shell.setAttribute("data-copilot", "expanded");
    var chatTab = document.querySelector('[data-rmc-copilot-tab="chat"]');
    if (chatTab) chatTab.click();
  }

  function closeHelpPanel() {
    var panel = document.querySelector("[data-rmc-tools-help-panel]");
    if (!panel) return;
    panel.hidden = true;
    panel.classList.remove("is-open");
  }

  function openHelpPanel() {
    var panel = document.querySelector("[data-rmc-tools-help-panel]");
    if (!panel) return;
    panel.hidden = false;
    panel.classList.add("is-open");
    var first = panel.querySelector("button");
    if (first) first.focus();
  }

  function startWalkthrough() {
    if (window.RMCTour && typeof window.RMCTour.pageContextFromDom === "function") {
      var ctx = window.RMCTour.pageContextFromDom();
      if (ctx && typeof window.RMCTour.fetchAndRun === "function") {
        window.RMCTour.fetchAndRun(ctx);
        return;
      }
    }
    var trigger = document.querySelector("[data-rmc-tour-start], [data-tour-start], .rmc-tour-fab");
    if (trigger) {
      trigger.click();
      return;
    }
    var shortcuts = document.querySelector("[data-rmc-kbd-cheatsheet-trigger]");
    if (shortcuts) shortcuts.click();
  }

  function contactSupport() {
    var quick = document.querySelector("[data-rmc-support-quick-create]");
    if (quick) {
      quick.click();
      return;
    }
    if (window.RMCSupportQuickCreate && window.RMCSupportQuickCreate.open) {
      window.RMCSupportQuickCreate.open();
    }
  }

  function bindRoot(root) {
    var menu = root.querySelector("[data-rmc-header-utilities]");
    var search = root.querySelector("[data-rmc-util-search]");
    if (!menu) return;

    root.addEventListener("click", function (event) {
      var item = event.target.closest("[data-rmc-util-key]");
      if (!item || !root.contains(item)) return;
      recordRecent(root, item.getAttribute("data-rmc-util-key"));
      if (item.hasAttribute("data-rmc-util-open-copilot")) {
        event.preventDefault();
        openCopilot();
      }
    });

    if (search) {
      search.addEventListener("input", function () {
        applyFilter(root, search.value);
      });
    }

    root.addEventListener("shown.bs.dropdown", function () {
      renderRecents(root);
      if (search) {
        search.value = "";
        applyFilter(root, "");
        search.focus();
      }
    });

    menu.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        var trigger = root.querySelector(".rmc-header-utilities__trigger");
        if (window.bootstrap && trigger) {
          var instance = window.bootstrap.Dropdown.getInstance(trigger);
          if (instance) instance.hide();
        }
        if (trigger) trigger.focus();
        return;
      }
      trapTab(event, menu);
    });
  }

  function bindHelpPanel() {
    var panel = document.querySelector("[data-rmc-tools-help-panel]");
    if (!panel) return;
    var copilot = panel.querySelector("[data-rmc-tools-help-copilot]");
    var tour = panel.querySelector("[data-rmc-tools-help-tour]");
    var support = panel.querySelector("[data-rmc-tools-help-support]");
    if (copilot) {
      copilot.addEventListener("click", function () {
        closeHelpPanel();
        openCopilot();
      });
    }
    if (tour) {
      tour.addEventListener("click", function () {
        closeHelpPanel();
        startWalkthrough();
      });
    }
    if (support) {
      support.addEventListener("click", function () {
        closeHelpPanel();
        contactSupport();
      });
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && panel.classList.contains("is-open")) {
        closeHelpPanel();
      }
    });
    document.addEventListener("click", function (event) {
      if (!panel.classList.contains("is-open")) return;
      if (panel.contains(event.target)) return;
      if (event.target.closest("[data-rmc-assist-slot-id='help']")) return;
      closeHelpPanel();
    });
  }

  var LIVE_BANNER_KEY = "rmc.headerLiveBanner.dismissed.v1";

  function liveBannerDismissed() {
    try {
      return window.sessionStorage.getItem(LIVE_BANNER_KEY) === "1";
    } catch (_err) {
      return false;
    }
  }

  function bindLiveBanners() {
    var banners = document.querySelectorAll("[data-rmc-header-live-dismissible]");
    if (!banners.length) return;
    banners.forEach(function (banner) {
      if (liveBannerDismissed()) {
        banner.hidden = true;
        return;
      }
      var btn = banner.querySelector("[data-rmc-header-live-dismiss]");
      if (!btn) return;
      btn.addEventListener("click", function () {
        banner.hidden = true;
        try {
          window.sessionStorage.setItem(LIVE_BANNER_KEY, "1");
        } catch (_err) {}
      });
    });
  }

  function init() {
    document.querySelectorAll("[data-rmc-header-utilities-root]").forEach(bindRoot);
    bindHelpPanel();
    bindLiveBanners();
    window.rmcOpenToolsHelpPanel = openHelpPanel;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
