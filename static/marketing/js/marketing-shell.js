/**
 * Marketing shell: nav toggle, sticky CTA bar. No dashboard/tenant logic.
 */
(function () {
  'use strict';

  function onDOMReady(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  onDOMReady(function () {
    var navToggler = document.querySelector('.mkt-navbar [data-bs-toggle="collapse"]');
    if (navToggler && typeof window.bootstrap !== 'undefined') {
      navToggler.setAttribute('aria-expanded', 'false');
    }

    var stickyBar = document.getElementById('mkt-sticky-cta-bar');
    if (stickyBar) {
      var hero = document.querySelector('.mkt-hero');
      function checkScroll() {
        if (!hero) return;
        var heroBottom = hero.getBoundingClientRect().bottom;
        if (heroBottom < 0) stickyBar.classList.add('is-visible');
        else stickyBar.classList.remove('is-visible');
      }
      window.addEventListener('scroll', checkScroll, { passive: true });
      checkScroll();
    }
  });
})();
