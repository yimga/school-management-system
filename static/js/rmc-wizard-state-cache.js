/* rmc-wizard-state-cache.js — CSP-safe localStorage wrapper for wizard state.
 *
 * Public API:
 *   RmcWizardStateCache.save(schoolId, wizardKey, state)
 *   RmcWizardStateCache.load(schoolId, wizardKey)   -> state | null
 *   RmcWizardStateCache.clear(schoolId, wizardKey)
 *   RmcWizardStateCache.clearAll(schoolId)
 *   RmcWizardStateCache.isPresent(schoolId, wizardKey) -> boolean
 *   RmcWizardStateCache.getSavedAtIso(schoolId, wizardKey) -> string | null
 *   RmcWizardStateCache.SCHEMA_VERSION
 *
 * Invariants:
 *   - Schema-version mismatch on load → drop + return null (silent).
 *   - TTL (30 days) expiry → drop + return null (silent).
 *   - Quota exceeded → emit beacon to /api/wizards/telemetry/cache-quota/ (best-effort).
 *   - No PII stored — server-side filtering handles this; client trusts what it receives.
 */
(function () {
  'use strict';

  if (typeof window === 'undefined') return;

  var SCHEMA_VERSION = 1;
  var TTL_MS = 30 * 24 * 60 * 60 * 1000;
  var KEY_PREFIX = 'rmc.wizard';

  function makeKey(schoolId, wizardKey) {
    return KEY_PREFIX + '.' + String(schoolId) + '.' + String(wizardKey) + '.v' + SCHEMA_VERSION;
  }

  function safeNow() { return Date.now(); }

  function emitBeacon(wizardKey, event) {
    try {
      if (!navigator.sendBeacon) return;
      var fd = new FormData();
      fd.set('wizard_key', wizardKey);
      fd.set('event', event);
      var beaconUrl =
        (window.RMCPlatformSurface && window.RMCPlatformSurface.url('wizard_cache_telemetry')) || '';
      if (!beaconUrl) return;
      navigator.sendBeacon(beaconUrl, fd);
    } catch (_e) { /* ignore */ }
  }

  function save(schoolId, wizardKey, state) {
    if (!schoolId || !wizardKey || !state) return false;
    var key = makeKey(schoolId, wizardKey);
    var payload = {
      schema_version: SCHEMA_VERSION,
      saved_at_ms: safeNow(),
      state: state
    };
    try {
      window.localStorage.setItem(key, JSON.stringify(payload));
      return true;
    } catch (err) {
      // QuotaExceededError or storage disabled
      emitBeacon(wizardKey, 'quota_exceeded');
      return false;
    }
  }

  function load(schoolId, wizardKey) {
    if (!schoolId || !wizardKey) return null;
    var key = makeKey(schoolId, wizardKey);
    var raw;
    try {
      raw = window.localStorage.getItem(key);
    } catch (_e) { return null; }
    if (!raw) return null;
    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (_e) {
      try { window.localStorage.removeItem(key); } catch (_e2) {}
      return null;
    }
    if (!parsed || parsed.schema_version !== SCHEMA_VERSION) {
      try { window.localStorage.removeItem(key); } catch (_e2) {}
      emitBeacon(wizardKey, 'schema_mismatch');
      return null;
    }
    if (typeof parsed.saved_at_ms !== 'number' || (safeNow() - parsed.saved_at_ms) > TTL_MS) {
      try { window.localStorage.removeItem(key); } catch (_e2) {}
      return null;
    }
    return parsed.state || null;
  }

  function clear(schoolId, wizardKey) {
    if (!schoolId || !wizardKey) return;
    var key = makeKey(schoolId, wizardKey);
    try { window.localStorage.removeItem(key); } catch (_e) {}
    emitBeacon(wizardKey, 'cleared');
  }

  function clearAll(schoolId) {
    if (!schoolId) return;
    var prefix = KEY_PREFIX + '.' + String(schoolId) + '.';
    var toDelete = [];
    try {
      for (var i = 0; i < window.localStorage.length; i++) {
        var k = window.localStorage.key(i);
        if (k && k.indexOf(prefix) === 0) toDelete.push(k);
      }
      toDelete.forEach(function (k) { window.localStorage.removeItem(k); });
    } catch (_e) {}
  }

  function isPresent(schoolId, wizardKey) {
    if (!schoolId || !wizardKey) return false;
    var key = makeKey(schoolId, wizardKey);
    try {
      return window.localStorage.getItem(key) !== null;
    } catch (_e) { return false; }
  }

  function getSavedAtIso(schoolId, wizardKey) {
    if (!schoolId || !wizardKey) return null;
    var key = makeKey(schoolId, wizardKey);
    var raw;
    try { raw = window.localStorage.getItem(key); } catch (_e) { return null; }
    if (!raw) return null;
    try {
      var parsed = JSON.parse(raw);
      if (parsed && typeof parsed.saved_at_ms === 'number') {
        return new Date(parsed.saved_at_ms).toISOString();
      }
    } catch (_e) {}
    return null;
  }

  window.RmcWizardStateCache = {
    save: save,
    load: load,
    clear: clear,
    clearAll: clearAll,
    isPresent: isPresent,
    getSavedAtIso: getSavedAtIso,
    SCHEMA_VERSION: SCHEMA_VERSION
  };
})();
