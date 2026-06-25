/**
 * Offline-first cache for /api/school/readiness/ (batches 1732–1733, Pillar E).
 * Dexie primary (offline-db.js v6); localStorage fallback.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "rmc_school_readiness_v1";

  function readCacheLocal(schoolKey) {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var blob = JSON.parse(raw);
      if (!blob || typeof blob !== "object") return null;
      if (schoolKey && blob.schoolKey && blob.schoolKey !== schoolKey) return null;
      return blob;
    } catch (_e) {
      return null;
    }
  }

  function writeCacheLocal(schoolKey, payload) {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          schoolKey: schoolKey || "",
          payload: payload,
          storedAt: Date.now(),
        })
      );
    } catch (_e) {
      /* quota or private mode */
    }
  }

  function readCache(schoolKey, callback) {
    var key = schoolKey || "default";
    var db = window.SMSOfflineDB;
    if (db && typeof db.getSchoolReadiness === "function") {
      db.getSchoolReadiness(key).then(function (row) {
        if (row && row.payload) {
          callback({
            schoolKey: key,
            payload: row.payload,
            storedAt: row.updated_at || Date.now(),
            source: "dexie",
          });
          return;
        }
        callback(readCacheLocal(key));
      }).catch(function () {
        callback(readCacheLocal(key));
      });
      return;
    }
    callback(readCacheLocal(key));
  }

  function writeCache(schoolKey, payload) {
    var key = schoolKey || "default";
    writeCacheLocal(key, payload);
    var db = window.SMSOfflineDB;
    if (db && typeof db.putSchoolReadiness === "function") {
      db.putSchoolReadiness(key, payload);
    }
    if (payload && payload.lifecycle && db && typeof db.putOperationalLifecycle === "function") {
      db.putOperationalLifecycle(key, payload.lifecycle);
    }
  }

  function formatStaleAge(ms) {
    if (!ms || ms < 0) return "";
    var mins = Math.floor(ms / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return String(mins) + "m ago";
    var hrs = Math.floor(mins / 60);
    if (hrs < 48) return String(hrs) + "h ago";
    return String(Math.floor(hrs / 24)) + "d ago";
  }

  window.RMCSchoolReadinessCache = {
    read: function (schoolKey, callback) {
      if (typeof callback === "function") {
        readCache(schoolKey, callback);
        return;
      }
      return readCacheLocal(schoolKey);
    },
    write: writeCache,
    formatStaleAge: formatStaleAge,
    storageKey: STORAGE_KEY,
  };
})();
