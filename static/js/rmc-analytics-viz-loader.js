/**
 * Lazy-load unified analytics viz IIFE when mount nodes enter viewport (or idle).
 * Pairs with templates/partials/rmc_analytics_viz_bundle.html
 */
(function () {
  'use strict';

  var DEFAULT_SRC = '/static/js/dist/rmc-analytics-dashboard.iife.js';
  var loaded = false;

  function resolveSrc() {
    var el = document.querySelector('[data-rmc-tenant-overview][data-bundle-src]');
    if (el && el.getAttribute('data-bundle-src')) {
      return el.getAttribute('data-bundle-src');
    }
    return DEFAULT_SRC;
  }

  function injectBundle(src) {
    if (loaded) return;
    loaded = true;
    var script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.dataset.rmcAnalyticsBundle = '1';
    document.head.appendChild(script);
  }

  function scheduleLoad() {
    var src = resolveSrc();
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(function () { injectBundle(src); }, { timeout: 2500 });
      return;
    }
    setTimeout(function () { injectBundle(src); }, 1);
  }

  function observeMounts() {
    var mounts = document.querySelectorAll('[data-rmc-tenant-overview]');
    if (!mounts.length) return;
    if (!('IntersectionObserver' in window)) {
      scheduleLoad();
      return;
    }
    var observer = new IntersectionObserver(
      function (entries) {
        for (var i = 0; i < entries.length; i++) {
          if (entries[i].isIntersecting) {
            observer.disconnect();
            scheduleLoad();
            return;
          }
        }
      },
      { rootMargin: '120px' }
    );
    mounts.forEach(function (node) { observer.observe(node); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', observeMounts);
  } else {
    observeMounts();
  }
})();
