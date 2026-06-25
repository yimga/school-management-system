/**
 * Poll /api/school/readiness/ and refresh the unified journey train (batch 1731+).
 * Offline-first: serve cached payload when fetch fails (batches 1732–1733).
 */
(function () {
  "use strict";

  function qs(root, sel) {
    return (root || document).querySelector(sel);
  }

  function qsa(root, sel) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function schoolKeyFromRoot(root) {
    return root.getAttribute("data-rmc-readiness-school-key") || "";
  }

  function setStaleBanner(root, visible, label) {
    var banner = qs(root, "[data-rmc-readiness-stale='1']");
    if (!banner) return;
    banner.hidden = !visible;
    if (label) {
      var span = qs(banner, "[data-rmc-readiness-stale-label='1']");
      if (span) span.textContent = label;
    }
  }

  function syncTrain(root, payload, meta) {
    if (!payload || !payload.ok) return;
    var meter = qs(root, "[data-rmc-readiness-meter='1'] i");
    var meterWrap = qs(root, "[data-rmc-readiness-meter='1']");
    var pct = payload.meter_percent || 0;
    if (meter) meter.style.width = String(pct) + "%";
    if (meterWrap) meterWrap.setAttribute("aria-valuenow", String(pct));
    var ring = document.querySelector(".rmc-setup-surface__ring");
    if (ring) {
      ring.style.setProperty("--rmc-setup-ring-pct", String(pct) + "%");
      var ringVal = ring.querySelector(".rmc-setup-surface__ring-value");
      if (ringVal) ringVal.textContent = String(pct) + "%";
    }
    var slo = payload.provisioning_slo || {};
    var sloEl = qs(root, "[data-rmc-readiness-slo='1']");
    if (sloEl && slo.label) {
      sloEl.textContent = slo.label;
      sloEl.className =
        "rmc-readiness-train__slo rmc-readiness-train__slo--" +
        (slo.tone || "unknown");
    }
    var phases = payload.phases || [];
    phases.forEach(function (phase) {
      var li = qs(root, "[data-phase-key='" + phase.key + "']");
      if (!li) return;
      li.classList.toggle("is-done", !!phase.done);
      var detail = li.querySelector(".rmc-readiness-train__phase-detail");
      if (detail && phase.detail) detail.textContent = phase.detail;
    });
    var golive = document.querySelector("[data-rmc-execute-launch-form='1']");
    var launchReady = !!(payload.setup_studio && payload.setup_studio.launch_ready);
    if (golive) golive.hidden = !launchReady;

    if (meta && meta.stale) {
      var cacheApi = window.RMCSchoolReadinessCache;
      var age =
        cacheApi && meta.storedAt
          ? cacheApi.formatStaleAge(Date.now() - meta.storedAt)
          : "";
      setStaleBanner(
        root,
        true,
        age
          ? "Last updated " + age + " · showing cached readiness"
          : "Offline · showing cached readiness"
      );
    } else {
      setStaleBanner(root, false);
    }
  }

  function applyPayload(root, payload, meta) {
    syncTrain(root, payload, meta);
  }

  function poll(root) {
    var url = root.getAttribute("data-rmc-readiness-url");
    if (!url) return;
    var schoolKey = schoolKeyFromRoot(root);
    var cacheApi = window.RMCSchoolReadinessCache;

    if (typeof navigator !== "undefined" && navigator.onLine === false && cacheApi) {
      cacheApi.read(schoolKey, function (cached) {
        if (cached && cached.payload) {
          applyPayload(root, cached.payload, { stale: true, storedAt: cached.storedAt });
        }
      });
      return;
    }

    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (res) {
        if (!res.ok) throw new Error("readiness_http_" + res.status);
        return res.json();
      })
      .then(function (payload) {
        if (payload && cacheApi) {
          cacheApi.write(schoolKey, payload);
        }
        applyPayload(root, payload, { stale: false });
      })
      .catch(function () {
        if (!cacheApi) return;
        cacheApi.read(schoolKey, function (cached) {
          if (cached && cached.payload) {
            applyPayload(root, cached.payload, { stale: true, storedAt: cached.storedAt });
          }
        });
      });
  }

  function init() {
    qsa(document, "[data-rmc-readiness-train='1']").forEach(function (root) {
      var cacheApi = window.RMCSchoolReadinessCache;
      var schoolKey = schoolKeyFromRoot(root);
      if (cacheApi) {
        cacheApi.read(schoolKey, function (cached) {
          if (cached && cached.payload) {
            applyPayload(root, cached.payload, { stale: true, storedAt: cached.storedAt });
          }
        });
      }
      poll(root);
      window.setInterval(function () {
        poll(root);
      }, 60000);
    });
    window.addEventListener("online", function () {
      qsa(document, "[data-rmc-readiness-train='1']").forEach(poll);
    });
    document.addEventListener("rmc:reconnect-rehydrate", function () {
      qsa(document, "[data-rmc-readiness-train='1']").forEach(poll);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
