/**
 * Offline foundational (2026-05-11): hydrate the attendance roll-call form
 * from SMSOfflineDB when the page is opened offline.
 *
 * Activation: any element on the page that carries
 *   data-attendance-offline-hydrator="1"
 *   data-attendance-scope="student|teacher"
 *   data-attendance-classroom-id="<id>"           (student scope only)
 *   data-attendance-status-choices='[["present","Present"],...]'
 *
 * When the page loads and `navigator.onLine === false` AND the form's
 * <tbody> has no rows, this script reads SMSOfflineDB and renders one
 * row per cached student / teacher. The form keeps using its existing
 * offline-form-draft wiring; submissions get queued to the outbox as
 * before. Nothing is hydrated if the page already rendered server-side
 * rows (which is what we want — server data wins).
 *
 * Idempotent: safe to load on every page; the entry-gate looks for the
 * data attribute. No effect when SMSOfflineDB is unavailable.
 */
(function (global) {
  'use strict';

  var doc = global.document;
  if (!doc) return;

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function parseChoices(raw) {
    if (!raw) return [['present', 'Present'], ['absent', 'Absent'], ['late', 'Late']];
    try {
      var parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length) return parsed;
    } catch (e) {
      /* fall through */
    }
    return [['present', 'Present'], ['absent', 'Absent'], ['late', 'Late']];
  }

  function renderRow(name, id, choices) {
    var options = choices.map(function (c) {
      var v = c[0];
      var lbl = c[1] || c[0];
      return '<option value="' + escapeHtml(v) + '">' + escapeHtml(lbl) + '</option>';
    }).join('');
    return (
      '<tr data-rmc-offline-hydrated="1">' +
      '<td>' + escapeHtml(name) + '</td>' +
      '<td><select name="status_' + escapeHtml(id) + '" class="form-select form-select-sm status-select min-touch-target" style="min-height:2.75rem;">' +
      options +
      '</select></td>' +
      '</tr>'
    );
  }

  function hydrateStudents(host, tbody, choices) {
    if (!global.SMSOfflineDB || typeof global.SMSOfflineDB.getStudents !== 'function') return;
    var classroomId = host.getAttribute('data-attendance-classroom-id') || '';
    return global.SMSOfflineDB.getStudents().then(function (rows) {
      if (!Array.isArray(rows) || rows.length === 0) return;
      var filtered = classroomId
        ? rows.filter(function (r) { return String(r.classroom_id || '') === String(classroomId); })
        : rows;
      if (filtered.length === 0) return;
      var html = filtered.map(function (s) {
        var name = s.display_name || ('Student #' + s.id);
        return renderRow(name, s.id, choices);
      }).join('');
      tbody.innerHTML = html;
      host.setAttribute('data-rmc-offline-hydrated', '1');
    }).catch(function () { /* swallow */ });
  }

  function hydrateTeachers(host, tbody, choices) {
    if (!global.SMSOfflineDB || typeof global.SMSOfflineDB.open !== 'function') return;
    return global.SMSOfflineDB.open().then(function (db) {
      if (!db) return;
      // The mirror keeps teachers in the same `students` store under classroom_id="staff"
      // when seeded that way; if a dedicated table is added later this branch picks it up.
      var table = db.tables && db.tables.find(function (t) { return t.name === 'teachers'; });
      if (!table) return;
      return table.toArray().then(function (rows) {
        if (!Array.isArray(rows) || rows.length === 0) return;
        var html = rows.map(function (t) {
          var name = t.display_name || t.name || ('Teacher #' + t.id);
          return renderRow(name, t.id, choices);
        }).join('');
        tbody.innerHTML = html;
        host.setAttribute('data-rmc-offline-hydrated', '1');
      });
    }).catch(function () { /* swallow */ });
  }

  function findTbody(host) {
    var table = host.querySelector('table');
    if (!table) return null;
    var tbody = table.tBodies && table.tBodies[0];
    if (!tbody) return null;
    // Don't overwrite server-rendered rows.
    if (tbody.children && tbody.children.length > 0) return null;
    return tbody;
  }

  function hydrateIfOffline() {
    if (navigator && navigator.onLine === true) return;
    var hosts = doc.querySelectorAll('[data-attendance-offline-hydrator="1"]');
    if (!hosts.length) return;
    Array.prototype.forEach.call(hosts, function (host) {
      if (host.getAttribute('data-rmc-offline-hydrated') === '1') return;
      var tbody = findTbody(host);
      if (!tbody) return;
      var choices = parseChoices(host.getAttribute('data-attendance-status-choices'));
      var scope = host.getAttribute('data-attendance-scope') || 'student';
      if (scope === 'teacher') {
        hydrateTeachers(host, tbody, choices);
      } else {
        hydrateStudents(host, tbody, choices);
      }
    });
  }

  if (doc.readyState === 'loading') {
    doc.addEventListener('DOMContentLoaded', hydrateIfOffline);
  } else {
    hydrateIfOffline();
  }
  // Re-run when connectivity drops while page is open.
  global.addEventListener('offline', hydrateIfOffline);
})(typeof window !== 'undefined' ? window : this);
