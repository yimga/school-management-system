/**
 * Bootstrap 5 dropdowns: fixed Popper strategy + viewport boundary so menus
 * are never clipped by header overflow:hidden stacks.
 */
(function () {
  "use strict";

  var BOUNDARY = "viewport";
  var DISPLAY = "dynamic";
  var OFFSET = "0,8";

  function popperConfig() {
    return {
      strategy: "fixed",
      modifiers: [
        { name: "preventOverflow", options: { boundary: "viewport", altAxis: true } },
        { name: "flip", options: { boundary: "viewport", fallbackPlacements: ["bottom-end", "top-end", "bottom-start", "top-start"] } },
      ],
    };
  }

  function ensureToggleAttrs(toggle) {
    if (!toggle || toggle.getAttribute("data-bs-toggle") !== "dropdown") return;
    if (!toggle.getAttribute("data-bs-boundary")) {
      toggle.setAttribute("data-bs-boundary", BOUNDARY);
    }
    if (!toggle.getAttribute("data-bs-display")) {
      toggle.setAttribute("data-bs-display", DISPLAY);
    }
    if (!toggle.getAttribute("data-bs-offset")) {
      toggle.setAttribute("data-bs-offset", OFFSET);
    }
    if (!toggle.getAttribute("data-bs-auto-close")) {
      toggle.setAttribute("data-bs-auto-close", "outside");
    }
  }

  function initDropdown(toggle) {
    ensureToggleAttrs(toggle);
    if (typeof bootstrap === "undefined" || !bootstrap.Dropdown) return;
    var existing = bootstrap.Dropdown.getInstance(toggle);
    if (existing) {
      existing._config = existing._config || {};
      existing._config.boundary = BOUNDARY;
      existing._config.display = DISPLAY;
      existing._config.popperConfig = popperConfig();
      return;
    }
    bootstrap.Dropdown.getOrCreateInstance(toggle, {
      boundary: BOUNDARY,
      display: DISPLAY,
      offset: OFFSET,
      autoClose: "outside",
      popperConfig: popperConfig(),
    });
  }

  function scan(root) {
    (root || document).querySelectorAll('[data-bs-toggle="dropdown"]').forEach(initDropdown);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      scan(document);
    });
  } else {
    scan(document);
  }

  document.addEventListener("shown.bs.dropdown", function (ev) {
    var menu = ev.target && ev.target.querySelector ? ev.target.querySelector(".dropdown-menu.show") : null;
    if (menu) {
      menu.style.zIndex = "var(--rmc-dropdown-z, 1090)";
    }
  });

  if (typeof MutationObserver !== "undefined") {
    var obs = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        m.addedNodes.forEach(function (node) {
          if (node.nodeType !== 1) return;
          if (node.matches && node.matches('[data-bs-toggle="dropdown"]')) {
            initDropdown(node);
          }
          scan(node);
        });
      });
    });
    obs.observe(document.documentElement, { childList: true, subtree: true });
  }
})();
