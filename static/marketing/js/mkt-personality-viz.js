/**
 * Renders bar + spark paths from data-mkt-personality-seed on marketing viz panels.
 */
(function () {
  'use strict';

  function parseSeed(el) {
    var raw = el.getAttribute('data-mkt-personality-seed');
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function renderChart(panel, seed) {
    var svg = panel.querySelector('[data-mkt-viz-chart]');
    if (!svg || !seed || !seed.series || !seed.series.length) return;

    var bars = svg.querySelector('[data-mkt-viz-bars]');
    var spark = svg.querySelector('[data-mkt-viz-spark]');
    if (!bars) return;

    var series = seed.series;
    var max = 1;
    var i;
    for (i = 0; i < series.length; i += 1) {
      var v = Number(series[i].value) || 0;
      if (v > max) max = v;
    }

    var w = 320;
    var h = 100;
    var pad = 8;
    var barW = (w - pad * 2) / series.length - 4;
    var gradId = 'mkt-viz-grad-' + (seed.personality_id || 'default');
    var html = '';
    var points = [];

    for (i = 0; i < series.length; i += 1) {
      var val = Number(series[i].value) || 0;
      var bh = Math.max(4, (val / max) * (h - 20));
      var x = pad + i * (barW + 4);
      var y = h - bh;
      html +=
        '<rect x="' +
        x +
        '" y="' +
        y +
        '" width="' +
        barW +
        '" height="' +
        bh +
        '" rx="2" fill="url(#' +
        gradId +
        ')" opacity="0.9"/>';
      points.push(x + barW / 2 + ',' + y);
    }
    bars.innerHTML = html;
    if (spark && points.length > 1) {
      spark.setAttribute('d', 'M' + points.join(' L'));
    }
  }

  function boot() {
    document.querySelectorAll('[data-mkt-personality-viz]').forEach(function (panel) {
      var seed = parseSeed(panel);
      if (seed) {
        renderChart(panel, seed);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
