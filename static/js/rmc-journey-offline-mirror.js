/**
 * Journey offline mirrors — discipline list + lifecycle stale UX (Pillar E).
 */
(function () {
  "use strict";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function showOfflineHint(el, visible) {
    if (!el) return;
    el.classList.toggle("d-none", !visible);
    if (visible) el.hidden = false;
  }

  function renderDisciplineRows(tbody, rows) {
    if (!tbody || !rows || !rows.length) return;
    tbody.innerHTML = rows
      .map(function (inc) {
        return (
          "<tr><td>" +
          (inc.date || "") +
          "</td><td>" +
          (inc.incident_type || "") +
          "</td><td>—</td><td>" +
          (inc.severity || "") +
          "</td><td>" +
          (inc.mtss_tier || "") +
          "</td><td>" +
          (inc.status || "") +
          "</td><td>—</td></tr>"
        );
      })
      .join("");
  }

  function hydrateDisciplineMirror(url, schoolId) {
    var db = window.SMSOfflineDB;
    if (!db || !url || !schoolId) return;

    var tbody = qs("[data-rmc-discipline-mirror-body='1']");
    var banner = qs("[data-rmc-discipline-offline-banner='1']");

    function renderFromRows(rows) {
      renderDisciplineRows(tbody, rows);
      if (banner && typeof navigator !== "undefined" && navigator.onLine === false) {
        banner.hidden = false;
      }
    }

    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      db.getDisciplineIncidents(schoolId).then(renderFromRows);
      return;
    }

    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (res) {
        if (!res.ok) throw new Error("discipline_http");
        return res.json();
      })
      .then(function (payload) {
        var rows = payload && payload.incidents ? payload.incidents : [];
        db.putDisciplineIncidents(schoolId, rows);
      })
      .catch(function () {
        db.getDisciplineIncidents(schoolId).then(renderFromRows);
      });
  }

  function initPartialFailureOffline() {
    var banner = qs("[data-rmc-provision-partial-failure='1']");
    if (!banner) return;
    var offlineHint = qs("[data-rmc-provision-partial-offline='1']", banner);
    function sync() {
      var offline = typeof navigator !== "undefined" && navigator.onLine === false;
      showOfflineHint(offlineHint, offline);
    }
    sync();
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
  }

  function initLifecycleStale() {
    var strip = qs("[data-rmc-lifecycle-strip='1']");
    if (!strip) return;
    var schoolKey = strip.getAttribute("data-rmc-lifecycle-school-key") || "default";
    var staleEl = qs("[data-rmc-lifecycle-stale='1']", strip);
    var db = window.SMSOfflineDB;
    if (!db || typeof db.getOperationalLifecycle !== "function") return;

    db.getOperationalLifecycle(schoolKey).then(function (row) {
      if (!row || !staleEl) return;
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        staleEl.hidden = false;
        var cacheApi = window.RMCSchoolReadinessCache;
        var age =
          cacheApi && row.updated_at
            ? cacheApi.formatStaleAge(Date.now() - row.updated_at)
            : "";
        staleEl.textContent = age
          ? "Lifecycle cached · last updated " + age
          : "Offline · showing cached lifecycle state";
      }
    });
  }

  function init() {
    initPartialFailureOffline();
    initLifecycleStale();
    var root = qs("[data-rmc-discipline-mirror='1']");
    if (root) {
      hydrateDisciplineMirror(
        root.getAttribute("data-rmc-discipline-api-url"),
        parseInt(root.getAttribute("data-rmc-discipline-school-id") || "0", 10)
      );
    }
    window.addEventListener("online", function () {
      var rootEl = qs("[data-rmc-discipline-mirror='1']");
      if (rootEl) {
        hydrateDisciplineMirror(
          rootEl.getAttribute("data-rmc-discipline-api-url"),
          parseInt(rootEl.getAttribute("data-rmc-discipline-school-id") || "0", 10)
        );
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
