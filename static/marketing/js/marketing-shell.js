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

    // Disable submit buttons on form submit to prevent duplicate submissions.
    // Applies only to marketing forms (data-form-name attribute or .mkt-* class).
    document.querySelectorAll('form[data-form-name], form.mkt-form').forEach(function (form) {
      form.addEventListener('submit', function () {
        var btn = form.querySelector('button[type="submit"], input[type="submit"]');
        if (!btn || btn.disabled) return;
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        if (btn.tagName === 'BUTTON' && !btn.dataset.originalLabel) {
          btn.dataset.originalLabel = btn.innerHTML;
          btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>' +
            (btn.dataset.busyLabel || 'Submitting…');
        }
      });
    });
  });
})();
