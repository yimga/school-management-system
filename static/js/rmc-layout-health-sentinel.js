/* Layout health sentinel — ResizeObserver overflow telemetry (Zero-Friction Phase 1).
 *
 * Watches high-traffic layout roots for horizontal bleed and reports at most
 * once per view per session via the friction ingest endpoint.
 */
(function () {
  "use strict";

  if (window.RMC_LAYOUT_SENTINEL_DISABLED) {
    return;
  }

  var SELECTORS = [
    ".rmc-data-table",
    ".rmc-smart-action-hub",
    ".rmc-action-hub",
    ".statement-header",
    ".portal-page-body",
  ];

  function ingestUrl() {
    return (
      (window.RMCPlatformSurface && window.RMCPlatformSurface.url("friction_ingest")) ||
      ""
    );
  }

  function getCsrfToken() {
    var match = (document.cookie || "").match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  var reported = Object.create(null);

  function reportOverflow(el, scrollWidth, clientWidth) {
    var key = (el.className || el.tagName || "node") + ":" + scrollWidth;
    if (reported[key]) {
      return;
    }
    reported[key] = true;
    var endpoint = ingestUrl();
    if (!endpoint) {
      return;
    }
    try {
      var body = JSON.stringify({
        view_name: document.documentElement.getAttribute("data-rmc-shell-root") || "layout",
        kind: "layout_overflow",
        payload: {
          selector: el.className ? "." + String(el.className).split(/\s+/)[0] : el.tagName,
          scroll_width: scrollWidth,
          client_width: clientWidth,
          delta: scrollWidth - clientWidth,
        },
      });
      fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: body,
        credentials: "same-origin",
        keepalive: true,
      }).catch(function () {});
    } catch (_e) {
      /* non-blocking */
    }
  }

  function inspect(el) {
    if (!el || !el.getBoundingClientRect) {
      return;
    }
    var sw = el.scrollWidth;
    var cw = el.clientWidth;
    if (sw > cw + 2) {
      reportOverflow(el, sw, cw);
      el.setAttribute("data-rmc-layout-overflow", "1");
    } else {
      el.removeAttribute("data-rmc-layout-overflow");
    }
  }

  function bind(el) {
    inspect(el);
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    var ro = new ResizeObserver(function () {
      inspect(el);
    });
    ro.observe(el);
  }

  function init() {
    SELECTORS.forEach(function (sel) {
      document.querySelectorAll(sel).forEach(bind);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
