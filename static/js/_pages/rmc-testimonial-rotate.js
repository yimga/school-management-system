// rmc-testimonial-rotate.js — v3.55.2 (2026-05-21)
//
// Auto-rotating parent testimonial in `_community_band.html`.
//
// Honors:
//   - prefers-reduced-motion (no auto-rotation; user can still dot-click)
//   - document.visibilityState ("hidden" pauses rotation)
//   - user interaction (dot-click or hover both pause rotation)
//
// CSP-friendly: external script, no inline handlers.
// Idempotent: re-running the file (e.g. after partial swap-in) is safe.

(function () {
  'use strict';

  function initOne(root) {
    if (root.dataset.rmcTestimonialInited === '1') return;
    root.dataset.rmcTestimonialInited = '1';

    var quotes = root.querySelectorAll('[data-rmc-testimonial-quote]');
    var dots   = root.querySelectorAll('[data-rmc-testimonial-dot]');
    if (!quotes.length) return;

    var idx = 0;
    var paused = false;
    var rotateMs = parseInt(root.dataset.rmcTestimonialIntervalMs || '7000', 10);
    if (!isFinite(rotateMs) || rotateMs < 1500) rotateMs = 7000;

    function show(n) {
      idx = (n + quotes.length) % quotes.length;
      Array.prototype.forEach.call(quotes, function (q, i) {
        q.classList.toggle('is-active', i === idx);
      });
      Array.prototype.forEach.call(dots, function (d, i) {
        d.classList.toggle('is-active', i === idx);
      });
    }

    Array.prototype.forEach.call(dots, function (dot, i) {
      dot.addEventListener('click', function () {
        paused = true;
        show(i);
      });
    });

    root.addEventListener('mouseenter', function () { paused = true; });

    var reducedMotion = window.matchMedia
      ? window.matchMedia('(prefers-reduced-motion: reduce)')
      : null;

    setInterval(function () {
      if (paused) return;
      if (document.visibilityState === 'hidden') return;
      if (reducedMotion && reducedMotion.matches) return;
      show(idx + 1);
    }, rotateMs);
  }

  function initAll() {
    var roots = document.querySelectorAll('[data-rmc-testimonial]');
    Array.prototype.forEach.call(roots, initOne);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
