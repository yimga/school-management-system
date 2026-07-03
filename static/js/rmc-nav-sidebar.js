/**
 * rmc-nav-sidebar.js — Left nav sidebar rail + resize (v4.02.1)
 * Unified contract for manager app-shell + portal bootstrap columns.
 */
(function () {
  "use strict";

  if (window.RMCNavSidebar && window.RMCNavSidebar.initialized) {
    return;
  }

  var STORAGE_WIDTH = "rmc-nav-sidebar-width";
  var STORAGE_MODE = "rmc-nav-sidebar-mode";
  var RAIL_W = 44;
  var MIN_W = 200;
  var MAX_W = 420;
  var DEFAULT_W = 280;
  var STEP_KB = 32;

  function readConfig() {
    var el = document.getElementById("page-data-rmc-nav-sidebar");
    if (!el) return null;
    try {
      return JSON.parse(el.textContent || "null");
    } catch (_e) {
      return null;
    }
  }

  function px(n) {
    return Math.round(n) + "px";
  }

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  function parseWidth(raw, fallback) {
    var n = parseInt(String(raw || ""), 10);
    if (!n || n < MIN_W || n > MAX_W) return fallback;
    return n;
  }

  function findBootstrapCol(shell) {
    if (!shell) return null;
    return (
      shell.querySelector("#cp-sidebar-col") ||
      shell.querySelector("#portal-sidebar-col") ||
      shell.querySelector(".cp-sidebar-col") ||
      shell.querySelector(".portal-sidebar-col")
    );
  }

  function emitLayout(shell, mode, width) {
    try {
      window.dispatchEvent(
        new CustomEvent("rmc:shell-layout", {
          detail: {
            sidebarMode: mode,
            sidebarWidth: width,
            shell: shell,
          },
        })
      );
    } catch (_e) {
      /* noop */
    }
  }

  function applyPortalWidth(widthPx) {
    document.documentElement.style.setProperty("--portal-sidebar-width", px(widthPx));
  }

  function applyShell(shell, mode, widthPx) {
    if (!shell) return;
    shell.setAttribute("data-rmc-nav-sidebar", mode);
    if (mode === "rail") {
      shell.style.setProperty("--rmc-app-shell-sidebar-w", px(RAIL_W));
      applyPortalWidth(RAIL_W);
    } else {
      shell.style.setProperty("--rmc-app-shell-sidebar-w", px(widthPx));
      applyPortalWidth(widthPx);
    }
    var col = findBootstrapCol(shell) || findBootstrapCol(document);
    if (col) {
      col.classList.toggle("rmc-nav-sidebar--rail", mode === "rail");
      col.classList.toggle("sidebar-collapsed", mode === "rail");
      col.classList.toggle("portal-sidebar-collapsed", mode === "rail");
    }
    var handle = shell.querySelector(".rmc-nav-sidebar__resize-handle");
    if (handle) {
      handle.setAttribute("aria-valuenow", String(mode === "rail" ? RAIL_W : widthPx));
      handle.setAttribute("aria-hidden", mode === "rail" ? "true" : "false");
    }
    emitLayout(shell, mode, mode === "rail" ? RAIL_W : widthPx);
  }

  function bindShell(shell, cfg) {
    if (!shell || shell.getAttribute("data-rmc-nav-sidebar-bound") === "1") return;
    shell.setAttribute("data-rmc-nav-sidebar-bound", "1");

    var minW = parseWidth(cfg && cfg.min_width, MIN_W);
    var maxW = parseWidth(cfg && cfg.max_width, MAX_W);
    var defaultW = parseWidth(cfg && cfg.default_width, DEFAULT_W);
    var savedW = parseWidth(localStorage.getItem(STORAGE_WIDTH), defaultW);
    var handle = shell.querySelector(".rmc-nav-sidebar__resize-handle");
    if (handle) {
      handle.setAttribute("aria-valuemin", String(minW));
      handle.setAttribute("aria-valuemax", String(maxW));
      handle.setAttribute("aria-valuenow", String(savedW));
    }

    var savedMode = localStorage.getItem(STORAGE_MODE);
    var mode = savedMode === "rail" ? "rail" : "normal";
    if (!savedMode && localStorage.getItem("portal-sidebar-collapsed") === "true") {
      mode = "rail";
    }
    if (cfg && cfg.default_mode === "rail" && !savedMode) {
      mode = "rail";
    }

    applyShell(shell, mode, savedW);
    updateToggleButtons(shell, mode);

    function updateToggleButtons(activeShell, activeMode) {
      var expanded = activeMode !== "rail";
      activeShell.querySelectorAll(
        ".rmc-nav-sidebar__toggle, .portal-sidebar-collapse-toggle, .js-sidebar-toggle"
      ).forEach(function (btn) {
        btn.setAttribute("aria-expanded", String(expanded));
        btn.setAttribute(
          "aria-label",
          expanded ? "Collapse navigation to icon rail" : "Expand navigation sidebar"
        );
        btn.setAttribute(
          "title",
          expanded ? "Collapse navigation to icon rail" : "Expand navigation sidebar"
        );
        var icon = btn.querySelector(".bi-layout-sidebar-inset, .bi-layout-sidebar-inset-reverse");
        if (icon) {
          icon.classList.toggle("bi-layout-sidebar-inset", expanded);
          icon.classList.toggle("bi-layout-sidebar-inset-reverse", !expanded);
        }
      });
    }

    function persist(modeValue, widthValue) {
      localStorage.setItem(STORAGE_MODE, modeValue);
      if (modeValue !== "rail") {
        localStorage.setItem(STORAGE_WIDTH, String(widthValue));
      }
    }

    function readActiveWidth(activeShell, fallback) {
      var shellWidth = parseWidth(
        getComputedStyle(activeShell).getPropertyValue("--rmc-app-shell-sidebar-w"),
        0
      );
      if (shellWidth) return shellWidth;
      return parseWidth(
        getComputedStyle(document.documentElement).getPropertyValue("--portal-sidebar-width"),
        fallback
      );
    }

    function toggleMode() {
      var current = shell.getAttribute("data-rmc-nav-sidebar") || "normal";
      var next = current === "rail" ? "normal" : "rail";
      var width = parseWidth(localStorage.getItem(STORAGE_WIDTH), savedW);
      applyShell(shell, next, width);
      updateToggleButtons(shell, next);
      persist(next, width);
      localStorage.setItem("portal-sidebar-collapsed", next === "rail" ? "true" : "false");
    }

    shell.querySelectorAll(".rmc-nav-sidebar__toggle, .portal-sidebar-collapse-toggle, .js-sidebar-toggle").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        toggleMode();
      });
    });

    bindSidebarFilter(shell);

    if (handle) {
      handle.addEventListener("mousedown", function (e) {
        if (e.button !== 0) return;
        if ((shell.getAttribute("data-rmc-nav-sidebar") || "normal") === "rail") return;
        e.preventDefault();
        var startX = e.clientX;
        var startW = readActiveWidth(shell, savedW);

        function onMove(ev) {
          var next = clamp(startW + (ev.clientX - startX), minW, maxW);
          applyShell(shell, "normal", next);
        }

        function onUp() {
          var finalW = readActiveWidth(shell, startW);
          persist("normal", finalW);
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          document.body.style.cursor = "";
          document.body.style.userSelect = "";
        }

        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });

      handle.addEventListener("keydown", function (event) {
        if ((shell.getAttribute("data-rmc-nav-sidebar") || "normal") === "rail") return;
        var current = readActiveWidth(shell, savedW);
        var next = current;
        switch (event.key) {
          case "ArrowLeft":
          case "ArrowDown":
            next = clamp(current - STEP_KB, minW, maxW);
            break;
          case "ArrowRight":
          case "ArrowUp":
            next = clamp(current + STEP_KB, minW, maxW);
            break;
          case "Home":
            next = minW;
            break;
          case "End":
            next = maxW;
            break;
          default:
            return;
        }
        event.preventDefault();
        applyShell(shell, "normal", next);
        persist("normal", next);
      });
    }
  }

  function norm(value) {
    return String(value || "").trim().toLowerCase();
  }

  function itemText(item) {
    return norm(
      item.getAttribute("data-admin-search") ||
        item.getAttribute("title") ||
        item.textContent ||
        ""
    );
  }

  function setHidden(el, hidden) {
    if (!el) return;
    el.hidden = !!hidden;
    el.setAttribute("aria-hidden", hidden ? "true" : "false");
  }

  function bindSidebarFilter(shell) {
    var inputs = shell.querySelectorAll("[data-rmc-sidebar-filter-input]");
    if (!inputs.length) return;

    inputs.forEach(function (input) {
      if (input.getAttribute("data-rmc-sidebar-filter-bound") === "1") return;
      input.setAttribute("data-rmc-sidebar-filter-bound", "1");

      var mount = input.closest(".rmc-nav-sidebar__mount") || shell;
      var navs = Array.from(mount.querySelectorAll("[data-sidebar-nav='true'], [data-sidebar-nav]"));

      function applyFilter() {
        var query = norm(input.value);
        var active = query.length > 0;

        navs.forEach(function (nav) {
          var items = Array.from(
            nav.querySelectorAll(
              ".cp-sidebar__item, .nav-link, .admin-sidebar-link, .admin-sidebar-model-link, [data-admin-search]"
            )
          );

          items.forEach(function (item) {
            var match = !active || itemText(item).indexOf(query) !== -1;
            var wrapper = item.closest(".sidebar-nav-item-wrapper");
            setHidden(wrapper || item, !match);
          });

          Array.from(nav.querySelectorAll("details.cp-sidebar__group, .admin-sidebar-app-group")).forEach(function (group) {
            var visibleItems = Array.from(
              group.querySelectorAll(
                ".cp-sidebar__item, .nav-link, .admin-sidebar-link, .admin-sidebar-model-link, [data-admin-search]"
              )
            ).some(function (item) {
              var wrapper = item.closest(".sidebar-nav-item-wrapper");
              return !(wrapper || item).hidden;
            });
            setHidden(group, active && !visibleItems);
            if (active && visibleItems && group.tagName && group.tagName.toLowerCase() === "details") {
              group.open = true;
            }
          });

          Array.from(nav.querySelectorAll(".sidebar-section-title")).forEach(function (section) {
            var next = section.nextElementSibling;
            var hasVisible = false;
            while (next && !next.classList.contains("sidebar-section-title")) {
              if (!next.hidden) {
                hasVisible = true;
                break;
              }
              next = next.nextElementSibling;
            }
            setHidden(section, active && !hasVisible);
          });
        });
      }

      input.addEventListener("input", applyFilter);
      input.addEventListener("search", applyFilter);
    });

    if (shell.getAttribute("data-rmc-sidebar-slash-bound") !== "1") {
      shell.setAttribute("data-rmc-sidebar-slash-bound", "1");
      document.addEventListener("keydown", function (event) {
        if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
        var target = event.target;
        var tag = target && target.tagName ? target.tagName.toLowerCase() : "";
        if (tag === "input" || tag === "textarea" || tag === "select" || (target && target.isContentEditable)) return;
        var input = shell.querySelector("[data-rmc-sidebar-filter-input]");
        if (!input || input.offsetParent === null) return;
        event.preventDefault();
        input.focus();
      });
    }
  }

  function init() {
    var cfg = readConfig();
    if (cfg && cfg.enabled === false) return;

    var shells = Array.from(document.querySelectorAll(".rmc-app-shell"));
    if (!shells.length) {
      var bodyShell = document.body;
      if (
        bodyShell.classList.contains("manager-portal-bridge") ||
        document.getElementById("portal-sidebar-col") ||
        document.getElementById("cp-sidebar-col")
      ) {
        bindShell(bodyShell, cfg);
      }
      return;
    }
    shells.forEach(function (shell) {
      bindShell(shell, cfg);
    });
  }

  window.RMCNavSidebar = {
    initialized: true,
    init: init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
