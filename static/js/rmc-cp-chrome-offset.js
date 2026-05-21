/**
 * Measures sticky control-plane chrome height and sets --rmc-cp-chrome-offset
 * for sidebar sticky top + section-nav scroll padding.
 */
(function () {
  "use strict";

  function measure() {
    var chrome = document.querySelector(
      '[data-rmc-control-plane-chrome="1"], .rmc-control-plane-chrome'
    );
    if (!chrome) {
      chrome = document.getElementById("portalHeader");
    }
    if (!chrome && document.querySelector(".mkt-platform-header")) {
      chrome = document.querySelector(".mkt-platform-header");
    }
    var h = chrome ? Math.ceil(chrome.getBoundingClientRect().height) : 0;
    if (!h) {
      h = parseInt(
        getComputedStyle(document.documentElement).getPropertyValue(
          "--rmc-manager-header-height"
        ),
        10
      );
      if (!h || Number.isNaN(h)) {
        h = 64;
      }
      var body = document.body;
      if (
        body &&
        body.classList.contains("control-plane-shell") &&
        body.getAttribute("data-rmc-cp-scroll") === "document" &&
        !body.classList.contains("admin-manager-shell")
      ) {
        h += 52;
      }
    }
    document.documentElement.style.setProperty(
      "--rmc-cp-chrome-offset",
      h + "px"
    );
    return h;
  }

  function init() {
    measure();
    window.addEventListener("resize", measure, { passive: true });
    if (typeof ResizeObserver !== "undefined") {
      var ro = new ResizeObserver(measure);
      document
        .querySelectorAll(
          '[data-rmc-control-plane-chrome="1"], .rmc-control-plane-chrome, #portalHeader, .mkt-platform-header'
        )
        .forEach(function (node) {
          ro.observe(node);
        });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.RMC = window.RMC || {};
  window.RMC.measureCpChromeOffset = measure;
})();
