/**
 * rmc-text-overflow-tooltip.js — Typographic overflow guard runtime.
 * Marks clipped .rmc-text-container / [data-rmc-text-clamp] nodes and shows
 * a lightweight tooltip with full text on hover/focus (i18n-safe).
 */
(function () {
  "use strict";

  var TOOLTIP_ID = "rmc-text-overflow-tooltip";
  var SELECTOR =
    ".rmc-text-container, [data-rmc-text-clamp], [data-rmc-text-shield='1'], .rmc-text-shield, .modal-title, .form-label, .btn:not(.rmc-btn-wrap), .cp-primary-nav__pill, .tp-primary-nav__pill, .rmc-data-table td:not(.rmc-data-table__cell--wrap), .rmc-data-table th";

  function getTooltip(doc) {
    var el = doc.getElementById(TOOLTIP_ID);
    if (el) return el;
    el = doc.createElement("div");
    el.id = TOOLTIP_ID;
    el.className = "rmc-text-tooltip";
    el.setAttribute("role", "tooltip");
    el.hidden = true;
    doc.body.appendChild(el);
    return el;
  }

  function isOverflowing(node) {
    if (!node || !node.textContent || !node.textContent.trim()) return false;
    if (node.scrollWidth > node.clientWidth + 1) return true;
    if (node.scrollHeight > node.clientHeight + 1) return true;
    return false;
  }

  function fullText(node) {
    return (node.getAttribute("data-rmc-text-full") || node.textContent || "").trim();
  }

  function markOverflowNodes(root) {
    var nodes = (root || document).querySelectorAll(SELECTOR);
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (isOverflowing(node)) {
        node.setAttribute("data-rmc-text-overflow", "1");
        if (!node.getAttribute("title") && !node.getAttribute("aria-label")) {
          node.setAttribute("aria-label", fullText(node));
        }
      } else {
        node.removeAttribute("data-rmc-text-overflow");
      }
    }
  }

  function positionTooltip(tip, target) {
    var rect = target.getBoundingClientRect();
    var tipRect = tip.getBoundingClientRect();
    var top = rect.bottom + 8;
    var left = rect.left + rect.width / 2 - tipRect.width / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
    if (top + tipRect.height > window.innerHeight - 8) {
      top = rect.top - tipRect.height - 8;
    }
    tip.style.top = top + "px";
    tip.style.left = left + "px";
  }

  function bind(doc) {
    var tip = getTooltip(doc);
    var active = null;

    function show(target) {
      if (!target || target.getAttribute("data-rmc-text-overflow") !== "1") return;
      var text = fullText(target);
      if (!text) return;
      tip.textContent = text;
      tip.hidden = false;
      tip.setAttribute("data-rmc-text-tooltip-visible", "1");
      positionTooltip(tip, target);
      active = target;
    }

    function hide() {
      tip.hidden = true;
      tip.removeAttribute("data-rmc-text-tooltip-visible");
      active = null;
    }

    doc.addEventListener(
      "mouseover",
      function (ev) {
        var t = ev.target.closest("[data-rmc-text-overflow='1']");
        if (t) show(t);
      },
      true
    );

    doc.addEventListener(
      "focusin",
      function (ev) {
        var t = ev.target.closest("[data-rmc-text-overflow='1']");
        if (t) show(t);
      },
      true
    );

    doc.addEventListener(
      "mouseout",
      function (ev) {
        if (!active) return;
        if (ev.relatedTarget && active.contains(ev.relatedTarget)) return;
        hide();
      },
      true
    );

    doc.addEventListener(
      "focusout",
      function () {
        hide();
      },
      true
    );

    doc.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
  }

  function init() {
    markOverflowNodes(document);
    bind(document);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  document.addEventListener("htmx:afterSwap", function () {
    markOverflowNodes(document);
  });

  window.rmcTextOverflow = { refresh: markOverflowNodes };
})();
