/**
 * Live campus pulse — gentle stat jitter for hero dashboard mock (no deps).
 */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function jitterStat(node, formatter) {
    if (!node || reduced) return;
    var base = node.textContent.trim();
    var tick = 0;
    window.setInterval(function () {
      tick += 1;
      node.textContent = formatter(base, tick);
    }, 3200);
  }

  function boot() {
    document.querySelectorAll('[data-mkt-live-pulse]').forEach(function (root) {
      var attendance = root.querySelector('[data-mkt-pulse-stat="attendance"]');
      var buses = root.querySelector('[data-mkt-pulse-stat="buses"]');
      var grades = root.querySelector('[data-mkt-pulse-stat="grades"]');

      jitterStat(attendance, function () {
        var v = 96.8 + Math.random() * 1.2;
        return v.toFixed(1) + '%';
      });
      jitterStat(buses, function (_, tick) {
        return tick % 5 === 0 ? '11/12' : '12/12';
      });
      jitterStat(grades, function () {
        return Math.random() > 0.5 ? 'B+ avg' : 'A- avg';
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
