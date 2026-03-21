/**
 * RESILIENT_EDGE / N5: critical read surfaces — cache last good HTML while online;
 * when the browser goes offline on the same page, show a clear degraded-mode banner.
 * Does not replace service-worker document caching for full offline navigation.
 */
(function () {
  'use strict';

  var PREFIX = 'sms_critical_read_v1_';
  var bannerClass = 'sms-offline-critical-read-banner';

  function storageKey(el) {
    var k = el.getAttribute('data-sms-offline-read-cache-key') || '';
    return PREFIX + k.replace(/[^a-zA-Z0-9_-]/g, '_');
  }

  function saveSnapshot(el) {
    if (!el || !el.innerHTML || el.innerHTML.length < 20) return;
    try {
      var clone = el.cloneNode(true);
      clone.querySelectorAll('.' + bannerClass).forEach(function (n) {
        n.remove();
      });
      var html = clone.innerHTML;
      if (!html || html.length < 20) return;
      var payload = { savedAt: Date.now(), html: html };
      localStorage.setItem(storageKey(el), JSON.stringify(payload));
    } catch (_) {}
  }

  function removeBannerFor(el) {
    el.querySelectorAll('.' + bannerClass).forEach(function (n) {
      n.remove();
    });
  }

  function injectBanner(el, savedAt) {
    removeBannerFor(el);
    var div = document.createElement('div');
    div.className = 'alert alert-warning ' + bannerClass + ' mb-3';
    div.setAttribute('role', 'status');
    div.setAttribute('aria-live', 'polite');
    var when = '';
    if (savedAt) {
      try {
        when = new Date(savedAt).toLocaleString();
      } catch (_) {
        when = '';
      }
    }
    div.innerHTML =
      '<strong>Offline or unstable connection.</strong> ' +
      'You are viewing data that was last loaded in this browser' +
      (when ? ' (' + when + ').' : '. ') +
      'Reconnect and refresh to update.';
    el.insertBefore(div, el.firstChild);
  }

  function maybeRestoreFromStorage(el) {
    if (navigator.onLine) return false;
    try {
      var raw = localStorage.getItem(storageKey(el));
      if (!raw) return false;
      var data = JSON.parse(raw);
      if (!data || !data.html) return false;
      if (el.innerHTML && el.innerHTML.replace(/\s/g, '').length > 40) return false;
      el.innerHTML = data.html;
      injectBanner(el, data.savedAt);
      return true;
    } catch (_) {
      return false;
    }
  }

  function bind(el) {
    if (!el.getAttribute('data-sms-offline-read-cache-key')) return;

    function onOffline() {
      saveSnapshot(el);
      if (el.innerHTML && el.innerHTML.replace(/\s/g, '').length > 20) {
        try {
          var raw = localStorage.getItem(storageKey(el));
          var savedAt = raw ? JSON.parse(raw).savedAt : null;
          injectBanner(el, savedAt);
        } catch (_) {
          injectBanner(el, null);
        }
      }
    }

    function onOnline() {
      removeBannerFor(el);
      saveSnapshot(el);
    }

    window.addEventListener('offline', onOffline);
    window.addEventListener('online', onOnline);

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        maybeRestoreFromStorage(el);
        if (navigator.onLine) saveSnapshot(el);
        else if (el.innerHTML && el.innerHTML.replace(/\s/g, '').length > 20) onOffline();
      });
    } else {
      maybeRestoreFromStorage(el);
      if (navigator.onLine) saveSnapshot(el);
      else if (el.innerHTML && el.innerHTML.replace(/\s/g, '').length > 20) onOffline();
    }

    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && navigator.onLine) saveSnapshot(el);
    });
  }

  function init() {
    document.querySelectorAll('[data-sms-offline-read-cache-key]').forEach(bind);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
