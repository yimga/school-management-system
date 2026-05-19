/**
 * Marketing theme toggle — light default, explicit dark, or OS-following system.
 * FOUC-safe: inline bootstrap in base_marketing sets theme before paint.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'rmc-mkt-theme';
  var PLATFORM_KEY = 'runmycampus-theme-preference';
  var root = document.documentElement;
  var mediaQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function readStored() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (_) {
      return null;
    }
  }

  function systemTheme() {
    return mediaQuery && mediaQuery.matches ? 'dark' : 'light';
  }

  function normalizePreference(mode) {
    if (mode === 'dark' || mode === 'light' || mode === 'system') return mode;
    return 'light';
  }

  function setPressedState(preference, effectiveTheme) {
    document.querySelectorAll('[data-mkt-theme-toggle]').forEach(function (btn) {
      var label = effectiveTheme === 'dark' ? btn.getAttribute('data-label-light') : btn.getAttribute('data-label-dark');
      if (label) btn.setAttribute('aria-label', label);
      btn.setAttribute('aria-pressed', effectiveTheme === 'dark' ? 'true' : 'false');
    });
    document.querySelectorAll('[data-mkt-theme-choice]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-mkt-theme-choice') === preference ? 'true' : 'false');
    });
  }

  function applyTheme(mode) {
    var preference = normalizePreference(mode);
    var next = preference === 'system' ? systemTheme() : preference;
    root.setAttribute('data-theme-preference', preference);
    root.setAttribute('data-theme', next);
    try {
      localStorage.setItem(STORAGE_KEY, preference);
      localStorage.setItem(PLATFORM_KEY, preference);
    } catch (_) { /* ignore */ }
    try {
      window.dispatchEvent(new CustomEvent('rmc:theme-change', { detail: { preference: preference } }));
    } catch (_) { /* ignore */ }
    setPressedState(preference, next);
  }

  function initToggleButtons() {
    var stored = normalizePreference(readStored() || root.getAttribute('data-theme-preference') || root.getAttribute('data-theme'));
    applyTheme(stored);
    document.querySelectorAll('[data-mkt-theme-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var current = root.getAttribute('data-theme') || 'light';
        applyTheme(current === 'dark' ? 'light' : 'dark');
      });
    });
    document.querySelectorAll('[data-mkt-theme-choice]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyTheme(btn.getAttribute('data-mkt-theme-choice'));
      });
    });
    if (mediaQuery && mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', function () {
        if ((readStored() || 'light') === 'system') {
          applyTheme('system');
        }
      });
    } else if (mediaQuery && mediaQuery.addListener) {
      mediaQuery.addListener(function () {
        if ((readStored() || 'light') === 'system') {
          applyTheme('system');
        }
      });
    }
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
