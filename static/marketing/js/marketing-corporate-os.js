/**
 * Corporate OS shell behaviors: density preference + live status pill sync.
 */
(function () {
  'use strict';

  var DENSITY_KEY = 'rmc-os-density';
  var root = document.documentElement;

  function applyDensity(mode) {
    var value = mode === 'comfortable' || mode === 'compact' ? mode : 'standard';
    root.setAttribute('data-rmc-density', value);
    try {
      localStorage.setItem(DENSITY_KEY, value);
    } catch (_) { /* ignore */ }
    document.querySelectorAll('[data-rmc-density-choice]').forEach(function (btn) {
      var active = btn.getAttribute('data-rmc-density-choice') === value;
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function initDensity() {
    var stored = 'standard';
    try {
      stored = localStorage.getItem(DENSITY_KEY) || 'standard';
    } catch (_) { /* ignore */ }
    applyDensity(stored);
    document.querySelectorAll('[data-rmc-density-choice]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyDensity(btn.getAttribute('data-rmc-density-choice'));
      });
    });
  }

  function applyStatusPayload(payload) {
    if (!payload) return;
    var label = payload.overall_label || 'All systems operational';
    var status = payload.overall_status || 'operational';
    document.querySelectorAll('[data-mkt-status-label]').forEach(function (el) {
      el.textContent = label;
    });
    document.querySelectorAll('[data-mkt-status]').forEach(function (el) {
      el.classList.remove('rmc-os-status-overall--operational', 'rmc-os-status-overall--degraded', 'rmc-os-status-overall--outage');
      if (el.classList.contains('rmc-os-status-overall')) {
        el.classList.add('rmc-os-status-overall--' + status);
      }
    });
  }

  function refreshStatusPill() {
    fetch('/status/?format=json', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(applyStatusPayload)
      .catch(function () { /* keep SSR label */ });
  }

  function init() {
    initDensity();
    if (document.querySelector('[data-mkt-status]')) {
      refreshStatusPill();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
