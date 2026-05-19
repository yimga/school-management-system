/**
 * Marketing social-proof / testimonial / video interactions — guarded toggles.
 */
(function () {
  'use strict';

  function notify(msg) {
    if (window.RMCInteractionGuard && window.RMCInteractionGuard.notify) {
      window.RMCInteractionGuard.notify(msg, 'warning');
    } else if (typeof window.showToast === 'function') {
      window.showToast(msg, 'warning', 4000);
    }
  }

  function safe(fn) {
    return function (event) {
      try {
        return fn(event);
      } catch (err) {
        if (event && event.preventDefault) event.preventDefault();
        notify('This preview is temporarily unavailable. Please try again.');
        if (typeof console !== 'undefined' && console.error) {
          console.error('[mkt-proof-interactions]', err);
        }
      }
    };
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-mkt-testimonial-expand]').forEach(function (btn) {
      btn.addEventListener(
        'click',
        safe(function () {
          var card = btn.closest('.mkt-testimonial-card, .mkt-edt-testimonial');
          if (!card) return;
          var expanded = card.classList.toggle('is-expanded');
          btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        })
      );
    });

    document.querySelectorAll('.mkt-testimonial-card a[href="#"]').forEach(function (link) {
      if (link.getAttribute('data-rmc-dead-link-allow')) return;
      link.setAttribute('href', '/resources/case-studies/');
    });
  });
})();
