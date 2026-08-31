/**
 * rmc-isomorphic-grid-sweep.js — Secondary sweep runtime (v3.90.60)
 * Double-scroll detection, text-shield marking, empty-panel sweep, viewport sync.
 */
(function () {
  "use strict";

  var TEXT_SHIELD_SELECTOR = [
    // .rmc-info-tag__btn is exempt for the same reason .btn-link and
    // .dropdown-toggle are: it is an icon-only button with no label, so
    // there is nothing for the shield to clamp. Stamping it made the CSS
    // rule [data-rmc-text-shield] apply overflow:hidden, which CLIPPED the
    // invisible 24x24 touch region rmc-class-grammar.css gives it. Keep in
    // sync with the matching selector in rmc-isomorphic-grid-sweep.css.
    ".btn:not(.rmc-btn-wrap):not(.btn-link):not(.dropdown-toggle):not(.rmc-info-tag__btn)",
    ".cp-primary-nav__pill",
    ".tp-primary-nav__pill",
    ".modal-title",
    ".form-label:not(.rmc-label-wrap)",
    ".rmc-card__title",
    ".rmc-stat-card__label",
    ".rmc-stat-card__value",
    ".nav-link:not(.dropdown-toggle)",
    "input.form-control:not([type='hidden'])",
    "select.form-select",
    ".rmc-text-shield",
    "[data-rmc-text-shield='1']",
    ".rmc-text-container",
    "[data-rmc-text-clamp]",
  ].join(",");

  var SCROLL_ZONE_SELECTOR =
    ".rmc-app-shell__canvas, .rmc-app-shell__sidebar, [data-rmc-iso-scroll-zone='1'], .rmc-iso-split-pane__scroll, .rmc-iso-scroll-zone";

  var EMPTY_PANEL_SELECTOR = "[data-rmc-iso-panel='1']";

  function isIntentionalInnerScroll(el) {
    if (el.getAttribute("data-rmc-iso-scroll-zone") === "1") return true;
    var inline = el.getAttribute("style") || "";
    if (/max-height\s*:/i.test(inline) && /overflow-y\s*:\s*auto/i.test(inline)) return true;
    return false;
  }

  function isScrollable(el) {
    if (!el || el.nodeType !== 1) return false;
    var style = window.getComputedStyle(el);
    var oy = style.overflowY;
    if (oy !== "auto" && oy !== "scroll") return false;
    return el.scrollHeight > el.clientHeight + 2;
  }

  function isCanvasDescendant(el) {
    return !!el.closest(".rmc-app-shell__canvas");
  }

  function detectDoubleScroll(root) {
    var canvas = (root || document).querySelector(".rmc-app-shell__canvas");
    if (!canvas) return;
    var candidates = canvas.querySelectorAll("*");
    for (var i = 0; i < candidates.length; i++) {
      var node = candidates[i];
      if (node.matches(SCROLL_ZONE_SELECTOR)) continue;
      if (isIntentionalInnerScroll(node)) continue;
      if (node.closest(SCROLL_ZONE_SELECTOR) !== canvas && node.closest(SCROLL_ZONE_SELECTOR)) continue;
      if (isScrollable(node)) {
        node.setAttribute("data-rmc-double-scroll-risk", "1");
      } else {
        node.removeAttribute("data-rmc-double-scroll-risk");
      }
    }
  }

  function markTextShields(root) {
    var nodes = (root || document).querySelectorAll(TEXT_SHIELD_SELECTOR);
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (node.tagName === "TEXTAREA") continue;
      if (!node.getAttribute("data-rmc-text-shield")) {
        node.setAttribute("data-rmc-text-shield", "1");
      }
    }
    if (window.rmcTextOverflow && typeof window.rmcTextOverflow.refresh === "function") {
      window.rmcTextOverflow.refresh(root || document);
    }
  }

  function panelHasContent(panel) {
    if (panel.querySelector(".rmc-empty, .cp-empty, .tp-empty, .rmc-iso-panel-empty")) return true;
    var text = (panel.textContent || "").replace(/\s+/g, " ").trim();
    if (text.length > 0) return true;
    if (panel.querySelector("img, svg, canvas, table tbody tr, .rmc-data-table tbody tr")) return true;
    return false;
  }

  function sweepEmptyPanels(root) {
    var panels = (root || document).querySelectorAll(EMPTY_PANEL_SELECTOR);
    for (var i = 0; i < panels.length; i++) {
      var panel = panels[i];
      var records = panel.getAttribute("data-rmc-panel-records");
      var emptyByRecords = records === "0" || records === "false";
      var emptyByDom = !panelHasContent(panel);
      if (emptyByRecords || emptyByDom) {
        panel.setAttribute("data-rmc-panel-sweep-empty", "1");
        if (!panel.getAttribute("data-rmc-panel-empty-message")) {
          panel.setAttribute(
            "data-rmc-panel-empty-message",
            "No records logged yet. Click here to initialize your first entry."
          );
        }
      } else {
        panel.removeAttribute("data-rmc-panel-sweep-empty");
      }
    }
  }

  function syncViewportHeight() {
    var h = window.innerHeight;
    if (window.visualViewport && window.visualViewport.height) {
      h = window.visualViewport.height;
    }
    document.documentElement.style.setProperty("--rmc-iso-visual-viewport-h", h + "px");
  }

  function runSweep(root) {
    syncViewportHeight();
    detectDoubleScroll(root);
    markTextShields(root);
    sweepEmptyPanels(root);
  }

  function init() {
    runSweep(document);
    window.addEventListener("resize", syncViewportHeight);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", syncViewportHeight);
      window.visualViewport.addEventListener("scroll", syncViewportHeight);
    }
    document.addEventListener("htmx:afterSwap", function (ev) {
      runSweep(ev.detail && ev.detail.target ? ev.detail.target : document);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.rmcIsoGridSweep = {
    run: runSweep,
    detectDoubleScroll: detectDoubleScroll,
    markTextShields: markTextShields,
    sweepEmptyPanels: sweepEmptyPanels,
  };
})();
