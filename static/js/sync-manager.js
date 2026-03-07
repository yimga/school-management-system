/**
 * Sync manager: orchestrates "Sync now", post-sync hydration of the offline mirror,
 * and optional drip mode (throttle auto-replay when connection is weak).
 * Works with the existing service worker queue; does not duplicate queue logic.
 */
(function (global) {
  'use strict';

  var HYDRATE_AFTER_SYNC_KEY = 'sms-hydrate-after-sync';
  var DEFAULT_HYDRATE_ENDPOINTS = [
    { url: '/api/entities/students/', store: 'students', normalizer: 'student' },
    { url: '/api/attendance/', store: 'attendance', normalizer: 'attendance' },
    { url: '/api/entities/classrooms/', store: 'classrooms', normalizer: 'classroom' },
  ];

  function getConfig() {
    return global.SMS_OFFLINE_CONFIG || {};
  }

  /**
   * Whether the connection is considered weak (save data or slow effectiveType).
   * When true, automatic replay on 'online' can be skipped; user should use "Sync now".
   */
  function isConnectionWeak() {
    var conn = global.navigator && global.navigator.connection;
    if (!conn) return false;
    if (conn.saveData === true) return true;
    var et = (conn.effectiveType || '').toLowerCase();
    return et === '2g' || et === 'slow-2g' || et === '3g';
  }

  /**
   * Whether device is in a low-power state (Save Data or battery low/charging and level low).
   * Used when reduceActivityLowPower is enabled.
   */
  function isLowPower() {
    if (global.navigator && global.navigator.connection && global.navigator.connection.saveData === true) return true;
    if (!global.navigator.getBattery) return false;
    return global.navigator.getBattery().then(function (bat) {
      if (!bat) return false;
      return bat.level < 0.2 && !bat.charging;
    }).catch(function () { return false; });
  }

  /**
   * Whether drip mode is enabled (only replay on manual "Sync now"; skip auto-replay on online).
   * True when: (dripWhenWeak && connection weak) or (reduceActivityLowPower && low power).
   * Sync callers should use getDripModeSync() for synchronous check; getDripMode() is async when battery API is used.
   */
  function getDripModeSync() {
    var cfg = getConfig();
    if (cfg.dripWhenWeak !== false && isConnectionWeak()) return true;
    if (cfg.reduceActivityLowPower && global.navigator && global.navigator.connection && global.navigator.connection.saveData === true) return true;
    return false;
  }

  function getDripMode() {
    var cfg = getConfig();
    if (cfg.dripWhenWeak !== false && isConnectionWeak()) return Promise.resolve(true);
    if (!cfg.reduceActivityLowPower) return Promise.resolve(false);
    return isLowPower();
  }

  /**
   * Ask the service worker to replay the queue now (priority order: attendance → grade → api).
   * Call this from "Sync now" button; reachability check should be done by the caller (e.g. offline-status-bar).
   */
  function requestSyncNow() {
    if (!global.navigator.serviceWorker || !global.navigator.serviceWorker.controller) return;
    global.navigator.serviceWorker.controller.postMessage({ type: 'REPLAY_SYNC_NOW' });
  }

  /**
   * Ask the service worker to replay up to `limit` items per type (drip/batch). Use when connection is weak.
   * @param {number} [limit=10]
   */
  function requestSyncBatch(limit) {
    if (!global.navigator.serviceWorker || !global.navigator.serviceWorker.controller) return;
    var n = Math.min(Math.max(1, parseInt(limit, 10) || 10), 50);
    global.navigator.serviceWorker.controller.postMessage({ type: 'REPLAY_SYNC_BATCH', limit: n });
  }

  /**
   * Build hydrate options from config. Uses hydrateEndpoints from config or defaults.
   * Each endpoint can have { url, store, normalizer } where normalizer is a key in SMSOfflineDB.normalizers.
   */
  function getHydrateOptions() {
    var cfg = getConfig();
    var baseUrl = (cfg.baseUrl != null && cfg.baseUrl !== '') ? cfg.baseUrl : '';
    var list = (cfg.hydrateEndpoints && Array.isArray(cfg.hydrateEndpoints)) ? cfg.hydrateEndpoints : DEFAULT_HYDRATE_ENDPOINTS;
    var normalizers = (global.SMSOfflineDB && global.SMSOfflineDB.normalizers) || {};
    var endpoints = list.map(function (ep) {
      var norm = (ep.normalizer && normalizers[ep.normalizer]) || function (x) { return x; };
      return { url: ep.url, store: ep.store, normalize: norm };
    });
    return { baseUrl: baseUrl, endpoints: endpoints };
  }

  /**
   * Run hydration of the offline mirror (e.g. after sync-complete).
   * No-op if SMSOfflineDB is not available or hydrate is disabled in config.
   */
  function hydrateAfterSync() {
    var cfg = getConfig();
    if (cfg.hydrate === false || !global.SMSOfflineDB || typeof global.SMSOfflineDB.hydrate !== 'function') return Promise.resolve();
    var options = getHydrateOptions();
    return global.SMSOfflineDB.hydrate(options).catch(function () {});
  }

  /**
   * Listen for sync-complete and run hydration once.
   */
  function onSyncComplete() {
    hydrateAfterSync();
  }

  function init() {
    var cfg = getConfig();
    if (!cfg.enabled) return;

    if (global.navigator.serviceWorker) {
      global.navigator.serviceWorker.addEventListener('message', function (event) {
        var d = event.data;
        if (!d || d.type !== 'sync-complete') return;
        onSyncComplete();
      });
    }

    if (global.navigator.onLine && cfg.hydrate !== false && global.SMSOfflineDB && global.SMSOfflineDB.isAvailable()) {
      hydrateAfterSync();
    }
  }

  if (global.document && global.document.readyState === 'loading') {
    global.document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /**
   * Send a batch of delta payloads to the server (Phase 2). No-op if deltaEndpointUrl not in config.
   * @param {Array<{ entity_type: string, id: number, changes: object, updated_at?: string, client_item_id?: any }>} items
   * @returns {Promise<{ removed_ids: number[], failed_count: number, failed_items: Array }>}
   */
  function sendDeltaBatch(items) {
    var cfg = getConfig();
    var url = (cfg.deltaEndpointUrl || '').trim() || (cfg.baseUrl || '') + '/api/offline/delta/';
    if (!url || !url.startsWith('http') && !url.startsWith('/')) url = '/api/offline/delta/';
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: items }),
    }).then(function (r) { return r.json(); }).catch(function () { return { removed_ids: [], failed_count: items.length, failed_items: [] }; });
  }

  global.SMSSyncManager = {
    requestSyncNow: requestSyncNow,
    requestSyncBatch: requestSyncBatch,
    sendDeltaBatch: sendDeltaBatch,
    isConnectionWeak: isConnectionWeak,
    isLowPower: isLowPower,
    getDripMode: getDripMode,
    getDripModeSync: getDripModeSync,
    hydrateAfterSync: hydrateAfterSync,
    getHydrateOptions: getHydrateOptions,
  };
})(typeof window !== 'undefined' ? window : this);
