/**
 * RunMyCampus marketing sticky CTA bootstrap (v4.01.03).
 *
 * Reveals the single canonical Book-demo CTA bar after the hero scrolls out
 * of view, so every sectional CTA on the marketing landing can stay as
 * `.btn-outline-primary` while the page still has one persistent primary
 * conversion target. Honours session-scoped dismissal so an operator who
 * X's the bar doesn't see it again that session.
 *
 * Markup contract: see templates/schools/marketing_landing.html
 *   [data-rmc-sticky-cta]              — the bar (initially hidden)
 *   [data-rmc-sticky-cta-close]        — dismiss button
 *
 * CSS contract: static/css/marketing-home.css
 *   .rmc-mkt-sticky-cta.is-visible     — slides bar into view
 */
(function () {
  'use strict';
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return;
  }
  document.addEventListener('DOMContentLoaded', function () {
    var cta = document.querySelector('[data-rmc-sticky-cta]');
    if (!cta) {
      return;
    }
    var dismissed = false;
    try {
      dismissed = window.sessionStorage.getItem('rmc-mkt-sticky-cta-dismissed') === '1';
    } catch (e) {
      // sessionStorage disabled (Safari private mode etc.) — fail open.
    }
    if (dismissed) {
      return;
    }
    cta.hidden = false;
    var hero = document.querySelector('#hero') || document.querySelector('.mkt-hero');
    if (typeof window.IntersectionObserver === 'function' && hero) {
      var observer = new window.IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.intersectionRatio === 0) {
            cta.classList.add('is-visible');
          } else {
            cta.classList.remove('is-visible');
          }
        });
      }, { threshold: 0 });
      observer.observe(hero);
    } else {
      // IntersectionObserver unsupported — show bar immediately.
      cta.classList.add('is-visible');
    }
    var close = cta.querySelector('[data-rmc-sticky-cta-close]');
    if (close) {
      close.addEventListener('click', function () {
        cta.classList.remove('is-visible');
        try {
          window.sessionStorage.setItem('rmc-mkt-sticky-cta-dismissed', '1');
        } catch (e) {
          // ignore
        }
      });
    }
  });
})();
