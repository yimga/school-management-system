/**
 * Offline mirror DB for Resilient Edge – local-first read cache.
 * Uses Dexie (IndexedDB) when available; no-ops gracefully when Dexie is not loaded.
 * Django remains source of truth; this is a read cache hydrated from existing APIs.
 */
(function (global) {
  'use strict';

  var DB_NAME = 'sms-offline-mirror';
  var DB_VERSION = 2;
  var db = null;

  function getDexie() {
    return global.Dexie;
  }

  function isAvailable() {
    return typeof getDexie() === 'function';
  }

  /**
   * Open the mirror DB and create schema if needed. Idempotent.
   * @returns {Promise<Dexie|null>} Resolves to db instance or null if Dexie unavailable.
   */
  function open() {
    if (db) return Promise.resolve(db);
    var Dexie = getDexie();
    if (!Dexie) return Promise.resolve(null);
    try {
      db = new Dexie(DB_NAME);
      db.version(DB_VERSION).stores({
        students: 'id, school_id, classroom_id, updated_at',
        attendance: 'id, student_id, classroom_id, date, updated_at',
        evaluations: 'id, student_id, subject_assignment_id, updated_at',
        classrooms: 'id, school_id, updated_at',
        ocr_corrections: 'original, corrected, updated_at',
      });
      return db.open().then(function () { return db; });
    } catch (err) {
      return Promise.resolve(null);
    }
  }

  /**
   * Hydrate the mirror from API responses. Fetches each endpoint with credentials,
   * extracts list (results or array), normalizes items, then bulk-puts into the store.
   * @param {Object} options
   * @param {string} [options.baseUrl=''] - Base URL for relative endpoints.
   * @param {Array<{url: string, store: string, normalize?: function}>} options.endpoints - List of { url, store, normalize(item) }.
   * @returns {Promise<{ ok: boolean, store?: string, error?: string }[]>} Per-endpoint result.
   */
  function hydrate(options) {
    var baseUrl = (options && options.baseUrl) || '';
    var endpoints = (options && options.endpoints) || [];
    if (!endpoints.length) return Promise.resolve([]);

    return open().then(function (database) {
      if (!database) return endpoints.map(function () { return { ok: false, error: 'Dexie unavailable' }; });
      var base = baseUrl.replace(/\/$/, '');
      return Promise.all(
        endpoints.map(function (ep) {
          var url = (ep.url.indexOf('http') === 0 || ep.url.indexOf('//') === 0) ? ep.url : base + (ep.url.indexOf('/') === 0 ? ep.url : '/' + ep.url);
          var storeName = ep.store;
          var normalize = typeof ep.normalize === 'function' ? ep.normalize : function (item) { return item; };
          return fetch(url, { method: 'GET', credentials: 'same-origin', headers: { Accept: 'application/json' } })
            .then(function (res) {
              if (!res.ok) throw new Error('HTTP ' + res.status);
              return res.json();
            })
            .then(function (data) {
              var list = Array.isArray(data) ? data : (data && (data.results || data.data));
              if (!Array.isArray(list)) list = [];
              var store = database.table(storeName);
              var rows = list.map(function (item) {
                var row = normalize(item);
                if (row && typeof row === 'object' && row.id != null) return row;
                return null;
              }).filter(Boolean);
              if (rows.length === 0) return store.clear().then(function () { return { ok: true, store: storeName }; });
              return store.bulkPut(rows).then(function () { return { ok: true, store: storeName }; });
            })
            .then(function (out) { return out; })
            .catch(function (err) {
              return { ok: false, store: storeName, error: (err && err.message) || String(err) };
            });
        })
      );
    });
  }

  /**
   * Clear a single store (e.g. after sync or logout).
   * @param {string} storeName
   * @returns {Promise<void>}
   */
  function clearStore(storeName) {
    return open().then(function (database) {
      if (!database) return;
      var table = database.table(storeName);
      return table.clear();
    });
  }

  /**
   * Clear all mirror stores.
   * @returns {Promise<void>}
   */
  function clearAll() {
    return open().then(function (database) {
      if (!database) return;
      return Promise.all([
        database.students.clear(),
        database.attendance.clear(),
        database.evaluations.clear(),
        database.classrooms.clear(),
        database.ocr_corrections.clear(),
      ]);
    });
  }

  function getStudents() {
    return open().then(function (database) {
      if (!database) return [];
      return database.students.toArray();
    });
  }

  function getAttendanceForDate(dateStr) {
    return open().then(function (database) {
      if (!database) return [];
      return database.attendance.where('date').equals(dateStr).toArray();
    });
  }

  function getClassrooms() {
    return open().then(function (database) {
      if (!database) return [];
      return database.classrooms.toArray();
    });
  }

  function getEvaluations() {
    return open().then(function (database) {
      if (!database) return [];
      return database.evaluations.toArray();
    });
  }

  function addOcrCorrection(original, corrected) {
    return open().then(function (database) {
      if (!database) return;
      return database.ocr_corrections.put({
        original: String(original),
        corrected: String(corrected),
        updated_at: Date.now(),
      });
    });
  }

  function getOcrCorrection(original) {
    return open().then(function (database) {
      if (!database) return null;
      return database.ocr_corrections.where('original').equals(String(original)).first().then(function (r) { return r ? r.corrected : null; });
    });
  }

  /**
   * Default normalizers for common API shapes. Use in hydrate endpoints.
   */
  var normalizers = {
    student: function (item) {
      var first = (item && item.first_name) || '';
      var last = (item && item.last_name) || '';
      var u = (item && item.user) || {};
      var displayName = (first + ' ' + last).trim() || (u.first_name && u.last_name ? u.first_name + ' ' + u.last_name : '') || item.display_name || item.name || String(item.id);
      return {
        id: item.id,
        school_id: item.school_id || (item.school && item.school.id) || item.school,
        classroom_id: item.classroom_id || (item.classroom && item.classroom.id) || item.classroom,
        display_name: displayName,
        updated_at: item.updated_at || null,
      };
    },
    attendance: function (item) {
      return {
        id: item.id,
        student_id: item.student_id || (item.student && item.student.id) || item.student,
        classroom_id: item.classroom_id || (item.classroom && item.classroom.id) || item.classroom,
        date: item.date,
        status: item.status || 'unknown',
        updated_at: item.updated_at || null,
      };
    },
    classroom: function (item) {
      return {
        id: item.id,
        school_id: item.school_id || item.school,
        name: item.name || String(item.id),
        updated_at: item.updated_at || null,
      };
    },
    evaluation: function (item) {
      return {
        id: item.id,
        student_id: item.student_id || (item.student && item.student.id) || item.student,
        subject_assignment_id: item.subject_assignment_id || (item.subject_assignment && item.subject_assignment.id) || item.subject_assignment,
        updated_at: item.updated_at || null,
      };
    },
  };

  global.SMSOfflineDB = {
    isAvailable: isAvailable,
    open: open,
    hydrate: hydrate,
    clearStore: clearStore,
    clearAll: clearAll,
    getStudents: getStudents,
    getAttendanceForDate: getAttendanceForDate,
    getClassrooms: getClassrooms,
    getEvaluations: getEvaluations,
    addOcrCorrection: addOcrCorrection,
    getOcrCorrection: getOcrCorrection,
    normalizers: normalizers,
  };
})(typeof window !== 'undefined' ? window : this);
