/**
 * Marketing theme toggle — light default, explicit dark via data-theme.
 * FOUC-safe: inline bootstrap in base_marketing sets theme before paint.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'rmc-mkt-theme';
  var root = document.documentElement;

  function readStored() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (_) {
      return null;
    }
  }

  function applyTheme(mode) {
    var next = mode === 'dark' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (_) { /* ignore */ }
    document.querySelectorAll('[data-mkt-theme-toggle]').forEach(function (btn) {
      var label = next === 'dark' ? btn.getAttribute('data-label-light') : btn.getAttribute('data-label-dark');
      if (label) btn.setAttribute('aria-label', label);
      btn.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
    });
  }

  function initToggleButtons() {
    document.querySelectorAll('[data-mkt-theme-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var current = root.getAttribute('data-theme') || 'light';
        applyTheme(current === 'dark' ? 'light' : 'dark');
      });
    });
  }

  window.RunMyCampusMarketingTheme = {
    apply: applyTheme,
    readStored: readStored,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initToggleButtons);
  } else {
    initToggleButtons();
  }
})();
