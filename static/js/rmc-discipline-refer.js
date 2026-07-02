/**
 * Teacher discipline refer — POST /api/discipline/incidents/ (offline via SW queue).
 */
(function () {
  "use strict";

  function qs(sel) {
    return document.querySelector(sel);
  }

  function init() {
    var form = qs("#rmc-discipline-refer-form");
    if (!form) return;

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var successEl = qs("#discipline-refer-success");
      var queuedEl = qs("#discipline-refer-queued");
      if (successEl) successEl.classList.add("d-none");
      if (queuedEl) queuedEl.classList.add("d-none");

      var payload = {
        student_id: parseInt(qs("#discipline-student").value, 10),
        incident_type: qs("#discipline-type").value,
        mtss_tier: qs("#discipline-tier").value,
        severity: qs("#discipline-severity").value,
        description: qs("#discipline-desc").value,
        notify_parent: qs("#discipline-notify").checked,
      };

      // Resolve through the platform URL catalog first (deployment prefix /
      // host aware); the literal path is the last-resort fallback only.
      var incidentsUrl =
        (window.RMCPlatformSurface &&
          window.RMCPlatformSurface.url &&
          window.RMCPlatformSurface.url("discipline_incidents")) ||
        ((window.SMS_OFFLINE_CONFIG || {}).disciplineIncidentsUrl) ||
        "/api/discipline/incidents/";
      fetch(incidentsUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-CSRFToken":
            (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "",
        },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          return res.json().then(function (body) {
            return { ok: res.ok, status: res.status, body: body };
          });
        })
        .then(function (result) {
          if (result.status === 202 || (result.body && result.body.queued)) {
            if (queuedEl) {
              queuedEl.textContent =
                "Queued — will sync when connected. Parent will be notified after sync.";
              queuedEl.classList.remove("d-none");
            }
            form.reset();
            return;
          }
          if (result.ok && result.body && result.body.ok) {
            if (successEl) {
              successEl.textContent = "Referral recorded.";
              successEl.classList.remove("d-none");
            }
            form.reset();
            return;
          }
          if (queuedEl) {
            queuedEl.textContent = "Could not submit — try again when online.";
            queuedEl.classList.remove("d-none");
          }
        })
        .catch(function () {
          if (queuedEl) {
            queuedEl.textContent =
              "Queued offline — will sync when connected.";
            queuedEl.classList.remove("d-none");
          }
        });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
