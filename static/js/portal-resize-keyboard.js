/*
 * Pass 10: WCAG 2.1.1 — keyboard equivalence for the portal sidebar resize handle.
 *
 * Drags work through portal-sidebar.js; this script adds keyboard parity:
 *   - Tab / Shift+Tab to focus the handle
 *   - ArrowLeft / ArrowRight to nudge the sidebar (32px steps)
 *   - Home / End to jump to the configured min/max width
 *   - Reads aria-valuemin / aria-valuemax / aria-valuenow off the handle
 *   - Maintains aria-valuenow and writes the new width to the sidebar column
 *
 * Fail-safe: if the handle or sidebar element is missing, the script is a no-op.
 */
(function () {
  "use strict";

  function readInt(el, attr, fallback) {
    var raw = el && el.getAttribute(attr);
    var n = parseInt(raw, 10);
    return isNaN(n) ? fallback : n;
  }

  function applyWidth(sidebar, width) {
    if (!sidebar) return;
    sidebar.style.flex = "0 0 " + width + "px";
    sidebar.style.maxWidth = width + "px";
  }

  function init() {
    var handle = document.querySelector('[data-portal-resize-handle="1"]');
    if (!handle) return;
    var sidebar = document.getElementById(handle.getAttribute("aria-controls") || "portal-sidebar-col");
    if (!sidebar) return;

    var min = readInt(handle, "aria-valuemin", 200);
    var max = readInt(handle, "aria-valuemax", 480);
    var step = 32;
    var current = readInt(handle, "aria-valuenow", 280);

    handle.addEventListener("keydown", function (event) {
      var next = current;
      switch (event.key) {
        case "ArrowLeft":
        case "ArrowDown":
          next = Math.max(min, current - step);
          break;
        case "ArrowRight":
        case "ArrowUp":
          next = Math.min(max, current + step);
          break;
        case "Home":
          next = min;
          break;
        case "End":
          next = max;
          break;
        default:
          return;
      }
      event.preventDefault();
      if (next !== current) {
        current = next;
        handle.setAttribute("aria-valuenow", String(current));
        applyWidth(sidebar, current);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
