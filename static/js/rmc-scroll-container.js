/**
 * Shared scroll-root resolver for document-scroll control plane + portal shells.
 */
(function () {
  "use strict";

  function isScrollable(el) {
    if (!el) return false;
    var style = window.getComputedStyle(el);
    var overflowY = style.overflowY;
    var canScroll =
      overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay";
    return canScroll && el.scrollHeight > el.clientHeight + 1;
  }

  function scrollCandidates(mode) {
    if (mode === "canvas") {
      return [
        document.querySelector(".rmc-app-shell__canvas"),
        document.querySelector(".rmc-app-shell__canvas-body"),
        document.getElementById("cp-main-content"),
        document.getElementById("main-content"),
        document.querySelector(".portal-main-col"),
        document.querySelector(".portal-main"),
      ];
    }
    if (mode === "main") {
      return [
        document.querySelector(".cp-admin-main-scroll-pane"),
        document.getElementById("cp-main-content"),
        document.querySelector(".cp-main-col"),
        document.querySelector(".rmc-app-shell__canvas"),
        document.querySelector(".rmc-app-shell__canvas-body"),
      ];
    }
    return [
      document.getElementById("main-content"),
      document.querySelector(".portal-main-col"),
      document.getElementById("cp-main-content"),
      document.querySelector(".rmc-app-shell__canvas"),
      document.querySelector(".rmc-app-shell__canvas-body"),
      document.getElementById("main"),
    ];
  }

  function getScrollContainer() {
    var body = document.body;
    var mode = body && body.getAttribute("data-rmc-cp-scroll");
    if (mode === "document") {
      return null;
    }
    var candidates = scrollCandidates(mode || "canvas");
    var i;
    for (i = 0; i < candidates.length; i += 1) {
      if (isScrollable(candidates[i])) {
        return candidates[i];
      }
    }
    for (i = 0; i < candidates.length; i += 1) {
      if (candidates[i]) {
        return candidates[i];
      }
    }
    return null;
  }

  function getScrollListenerTargets() {
    var body = document.body;
    var mode = body && body.getAttribute("data-rmc-cp-scroll");
    var targets = scrollCandidates(mode === "document" ? "document" : mode || "canvas");
    if (mode === "document") {
      return [];
    }
    return targets.filter(function (el) {
      return !!el;
    });
  }

  function getScrollTop(container) {
    return container
      ? container.scrollTop
      : window.scrollY || document.documentElement.scrollTop;
  }

  function scrollToY(container, top, behavior) {
    if (container) {
      container.scrollTo({ top: top, behavior: behavior || "smooth" });
    } else {
      window.scrollTo({ top: top, behavior: behavior || "smooth" });
    }
  }

  window.RMC = window.RMC || {};
  window.RMC.getScrollContainer = getScrollContainer;
  window.RMC.getScrollListenerTargets = getScrollListenerTargets;
  window.RMC.getScrollTop = getScrollTop;
  window.RMC.scrollToY = scrollToY;
  window.RMC.getFoldHeight = function () {
    return Math.max(window.innerHeight || 0, 320);
  };
})();
