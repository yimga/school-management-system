/**
 * Auto-Pilot: prefetch URLs for offline in low-latency windows (e.g. when 4g or on schedule).
 * Fetches /api/offline/prefetch_urls/ then requests each URL so the service worker caches them.
 */
(function (global) {
  'use strict';

  var PREFETCH_INTERVAL_MS = 6 * 60 * 60 * 1000;
  var timer = null;

  function getConfig() {
    return global.SMS_OFFLINE_CONFIG || {};
  }

  function isLowLatencyWindow() {
    if (!global.navigator || !global.navigator.connection) return true;
    var et = (global.navigator.connection.effectiveType || '').toLowerCase();
    return et === '4g' || et === '5g';
  }

  /** True if prefetch is allowed at current local hour (e.g. prefetchAtHour === 2 runs at 2 AM). */
  function isPrefetchTimeWindow() {
    var cfg = getConfig();
    var atHour = cfg.prefetchAtHour;
    if (atHour == null || atHour === '' || typeof atHour !== 'number') return true;
    var now = new Date();
    return now.getHours() === (atHour | 0);
  }

  /** Ms until the next prefetchAtHour (e.g. next 2 AM). */
  function msUntilNextPrefetchHour() {
    var cfg = getConfig();
    var atHour = (cfg.prefetchAtHour | 0) % 24;
    var now = new Date();
    var next = new Date(now);
    next.setHours(atHour, 0, 0, 0);
    if (next <= now) next.setDate(next.getDate() + 1);
    return Math.max(60000, next - now);
  }

  function runPrefetch() {
    if (!isPrefetchTimeWindow() && getConfig().prefetchAtHour != null) return;
    if (!isLowLatencyWindow() && getConfig().prefetchAtHour == null) return;
    var cfg = getConfig();
    if (!cfg.enabled) return;
    var base = (cfg.baseUrl || '').trim() || '';
    var url = (base + '/api/offline/prefetch_urls/').replace(/\/+/g, '/');
    if (!url.startsWith('http')) url = global.location.origin + (url.startsWith('/') ? url : '/' + url);
    fetch(url, { method: 'GET', credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : { urls: [] }; })
      .then(function (data) {
        var urls = (data && data.urls && Array.isArray(data.urls)) ? data.urls : [];
        urls.forEach(function (u) {
          fetch(u, { method: 'GET', credentials: 'same-origin' }).catch(function () {});
        });
      })
      .catch(function () {});
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    runPrefetch();
    var cfg = getConfig();
    var atHour = cfg.prefetchAtHour;
    if (atHour != null && atHour !== '' && typeof atHour === 'number') {
      timer = setTimeout(schedule, msUntilNextPrefetchHour());
    } else {
      timer = setTimeout(schedule, PREFETCH_INTERVAL_MS);
    }
  }

  function init() {
    var cfg = getConfig();
    if (!cfg.enabled || cfg.autoPilot === false) return;
    if (global.document && global.document.readyState === 'loading') {
      global.document.addEventListener('DOMContentLoaded', function () {
        setTimeout(schedule, 5000);
      });
    } else {
      setTimeout(schedule, 5000);
    }
  }

  if (global.document) init();
  global.SMSAutoPilot = { runPrefetch: runPrefetch };
})(typeof window !== 'undefined' ? window : this);
