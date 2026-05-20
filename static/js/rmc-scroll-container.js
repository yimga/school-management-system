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

  function getScrollContainer() {
    var body = document.body;
    var mode = body && body.getAttribute("data-rmc-cp-scroll");
    if (mode === "document") {
      return null;
    }
    if (mode === "main") {
      var adminMain =
        document.getElementById("cp-main-content") ||
        document.querySelector(".cp-main-col");
      if (adminMain) return adminMain;
    }
    var main = document.getElementById("main");
    if (isScrollable(main)) return main;
    var cpMain =
      document.getElementById("cp-main-content") ||
      document.querySelector(".cp-main-col");
    if (isScrollable(cpMain)) return cpMain;
    var portalMain =
      document.getElementById("main-content") ||
      document.querySelector(".portal-main-col");
    if (isScrollable(portalMain)) return portalMain;
    return null;
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
  window.RMC.getScrollTop = getScrollTop;
  window.RMC.scrollToY = scrollToY;
  window.RMC.getFoldHeight = function () {
    return Math.max(window.innerHeight || 0, 320);
  };
})();
