/**
 * Shopify-style rotating hero word. Pauses on hover and reduced-motion.
 */
(function () {
  'use strict';

  var nodes = document.querySelectorAll('[data-mkt-rotate-words]');
  if (!nodes.length) return;

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  nodes.forEach(function (el) {
    var raw = el.getAttribute('data-mkt-rotate-words') || '';
    var words = raw.split('|').map(function (w) { return w.trim(); }).filter(Boolean);
    if (words.length < 2) return;

    var target = el.querySelector('[data-mkt-rotate-target]') || el;
    var idx = 0;
    target.textContent = words[0];

    if (reduced) return;

    var intervalMs = parseInt(el.getAttribute('data-mkt-rotate-interval') || '3200', 10);
    var timer = null;

    function tick() {
      idx = (idx + 1) % words.length;
      target.style.opacity = '0';
      window.setTimeout(function () {
        target.textContent = words[idx];
        target.style.opacity = '1';
      }, 180);
    }

    function start() {
      if (timer) return;
      timer = window.setInterval(tick, intervalMs);
    }

    function stop() {
      if (!timer) return;
      window.clearInterval(timer);
      timer = null;
    }

    start();
    el.addEventListener('mouseenter', stop);
    el.addEventListener('mouseleave', start);
    el.addEventListener('focusin', stop);
    el.addEventListener('focusout', start);
  });
})();
