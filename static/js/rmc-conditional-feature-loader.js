/**
 * Loads optional shell scripts/styles only when matching DOM markers exist.
 * Config: window.RMC_CONDITIONAL_FEATURES = [{ selector, js?, css?, defer? }, ...]
 */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
      return;
    }
    fn();
  }

  function loadCss(href) {
    if (!href || document.querySelector('link[rel="stylesheet"][href="' + href + '"]')) {
      return;
    }
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function loadJs(src, defer) {
    if (!src || document.querySelector('script[src="' + src + '"]')) {
      return;
    }
    var script = document.createElement("script");
    script.src = src;
    if (defer !== false) {
      script.defer = true;
    }
    document.body.appendChild(script);
  }

  ready(function () {
    var cfg = window.RMC_CONDITIONAL_FEATURES;
    if (!cfg || !cfg.length) {
      return;
    }
    cfg.forEach(function (item) {
      if (!item || !item.selector || !document.querySelector(item.selector)) {
        return;
      }
      if (item.css) {
        loadCss(item.css);
      }
      if (item.js) {
        loadJs(item.js, item.defer);
      }
    });
  });
})();
