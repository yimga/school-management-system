/**
 * Global Footprint Wow+ parity — void parallax, celebration, deltas, snapshot (lab W13–W20).
 */
(function () {
  "use strict";
  if (window.__rmcWorldGlobeWowPlus) return;
  window.__rmcWorldGlobeWowPlus = true;

  var section = document.querySelector("[data-rmc-globe-wow-plus]");
  if (!section) return;

  var mapShell = document.getElementById("rmc-world-globe-map-shell");
  var celebrateEl = document.getElementById("rmc-world-globe-celebrate");
  var lastSchoolsLive = null;
  var celebratedKeys = {};
  var wired = false;

  function parsePayload() {
    var el = document.getElementById("rmc-world-globe-data");
    if (!el || !el.textContent) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (_e) {
      return null;
    }
  }

  function featureEnabled(key) {
    var snap = window.__rmcOperatorFleetSnapshot || {};
    var features = snap.features || (parsePayload() || {}).features || {};
    if (Object.prototype.hasOwnProperty.call(features, key)) return !!features[key];
    return true;
  }

  function api() {
    return window.RMCWorldGlobe;
  }

  function setWowOn(on) {
    section.classList.toggle("lx-world--wow-on", !!on);
    if (api() && api().setWowMode) api().setWowMode(!!on);
    var shareVoid = document.getElementById("rmc-world-globe-void-share");
    var snapBtn = document.getElementById("rmc-world-globe-snapshot-export");
    if (shareVoid && on) shareVoid.hidden = false;
    if (snapBtn && on && featureEnabled("executive_snapshot")) snapBtn.hidden = false;
  }

  function revealVoidZones() {
    if (!featureEnabled("void_zones")) return;
    [
      "rmc-world-globe-void-viewport",
      "rmc-world-globe-void-caption",
      "rmc-world-globe-void-whisper",
      "rmc-world-globe-void-school-hours",
    ].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.hidden = false;
    });
  }

  function updatePresenceUi(count) {
    var wrap = document.getElementById("rmc-world-globe-presence");
    var text = document.getElementById("rmc-world-globe-presence-text");
    if (!wrap || !text || !featureEnabled("globe_presence")) return;
    if (count > 0) {
      wrap.hidden = false;
      text.textContent = count + " viewing";
    } else {
      wrap.hidden = true;
      text.textContent = "";
    }
  }

  function showRegionalDeltas(deltas) {
    if (!deltas || typeof deltas !== "object") return;
    Object.keys(deltas).forEach(function (region) {
      var delta = deltas[region];
      if (!delta) return;
      var row = section.querySelector('[data-rmc-region="' + region + '"].lx-world__legend-row');
      if (!row) return;
      var badge = row.querySelector(".lx-world__delta-badge");
      if (!badge) return;
      badge.hidden = false;
      badge.textContent = (delta > 0 ? "+" : "") + delta;
      badge.classList.toggle("lx-world__delta-badge--down", delta < 0);
      window.setTimeout(function () {
        badge.hidden = true;
        badge.textContent = "";
      }, 8000);
    });
  }

  function flashPulseList() {
    var list = document.getElementById("rmc-world-globe-pulse-list");
    if (!list || !list.firstElementChild) return;
    list.firstElementChild.classList.add("lx-world__fleet-pulse-item--flash");
    window.setTimeout(function () {
      if (list.firstElementChild) list.firstElementChild.classList.remove("lx-world__fleet-pulse-item--flash");
    }, 600);
  }

  function triggerCelebration(xPct, yPct) {
    if (!celebrateEl || !featureEnabled("celebration_bloom")) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    celebrateEl.style.left = (xPct != null ? xPct : 58) + "%";
    celebrateEl.style.top = (yPct != null ? yPct : 52) + "%";
    celebrateEl.classList.remove("lx-world__celebrate--pop");
    void celebrateEl.offsetWidth;
    celebrateEl.classList.add("lx-world__celebrate--pop");
  }

  function maybeCelebrateOnboard(bundle) {
    if (!bundle || typeof bundle.schools_live !== "number") return;
    var rev = bundle.operator_fleet_revision || bundle.globe_revision || "";
    if (lastSchoolsLive != null && bundle.schools_live > lastSchoolsLive) {
      var key = "onboard:" + rev;
      if (!celebratedKeys[key]) {
        celebratedKeys[key] = true;
        try {
          sessionStorage.setItem("rmc-globe-celebrated-" + key, "1");
        } catch (_e) {
          /* ignore */
        }
        triggerCelebration();
        setWowOn(true);
        var caption = document.getElementById("rmc-world-globe-void-caption-text");
        if (caption) caption.textContent = "SSE · new school live";
        flashPulseList();
      }
    }
    lastSchoolsLive = bundle.schools_live;
  }

  function renderExpansionRadar() {
    var wrap = document.getElementById("rmc-world-globe-expansion-radar");
    var copy = document.getElementById("rmc-world-globe-expansion-copy");
    if (!wrap || !copy) return;
    var payload = parsePayload() || {};
    var targets = payload.expansion_targets || [];
    if (!targets.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    var names = targets.map(function (t) {
      return t.region || t.name || "";
    }).filter(Boolean);
    copy.textContent =
      names.length +
      " GLOCAL target" +
      (names.length === 1 ? "" : "s") +
      " at wide zoom: " +
      names.join(", ");
  }

  function syncShareHash() {
    var hashEl = document.getElementById("rmc-world-globe-share-hash");
    if (!hashEl || !api() || !api().isReady()) return;
    try {
      var pov = api().getPointOfView ? api().getPointOfView() : null;
      if (!pov) return;
      hashEl.textContent =
        "#globe=" + pov.lat.toFixed(1) + "," + pov.lng.toFixed(1) + "," + (pov.altitude || 1.02).toFixed(2);
    } catch (_e) {
      /* ignore */
    }
  }

  function exportExecutiveSnapshot() {
    if (!featureEnabled("executive_snapshot")) return;
    var stage = document.getElementById("rmc-world-globe-stage");
    var canvas = stage ? stage.querySelector("canvas") : null;
    if (!canvas || !canvas.toBlob) return;
    canvas.toBlob(function (blob) {
      if (!blob) return;
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "runmycampus-globe-" + new Date().toISOString().slice(0, 10) + ".png";
      a.click();
      URL.revokeObjectURL(url);
    }, "image/png");
  }

  function wireVoidParallax() {
    if (!mapShell || !featureEnabled("void_parallax")) return;
    var zones = mapShell.querySelectorAll(".lx-world__void-zone");
    mapShell.addEventListener(
      "pointermove",
      function (ev) {
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        var rect = mapShell.getBoundingClientRect();
        var nx = (ev.clientX - rect.left) / rect.width - 0.5;
        var ny = (ev.clientY - rect.top) / rect.height - 0.5;
        zones.forEach(function (z, i) {
          var factor = 4 + (i % 3) * 2;
          z.style.transform =
            "translate(" + (-nx * factor).toFixed(1) + "px," + (-ny * factor).toFixed(1) + "px)";
        });
      },
      { passive: true }
    );
  }

  function wireSnapshotButton() {
    var btn = document.getElementById("rmc-world-globe-snapshot-export");
    if (!btn || btn.__rmcSnapWired) return;
    btn.__rmcSnapWired = true;
    btn.addEventListener("click", exportExecutiveSnapshot);
  }

  function wireFleetHandlers() {
    document.addEventListener("rmc:fleet-snapshot", function (ev) {
      var detail = ev.detail || {};
      if (featureEnabled("wow_enabled")) setWowOn(true);
      if (detail.regional_deltas) showRegionalDeltas(detail.regional_deltas);
      maybeCelebrateOnboard(detail);
      if (detail.aurora) {
        /* aurora applied by bridge */
      }
      renderExpansionRadar();
      syncShareHash();
    });

    document.addEventListener("rmc:globe-ready", function () {
      setWowOn(featureEnabled("wow_enabled"));
      revealVoidZones();
      renderExpansionRadar();
      syncShareHash();
      window.setInterval(syncShareHash, 4000);
    });

    document.addEventListener("rmc:globe-live-updated", function () {
      syncShareHash();
    });
  }

  function wireOnce() {
    if (wired) return;
    wired = true;
    wireVoidParallax();
    wireSnapshotButton();
    wireFleetHandlers();
    if (featureEnabled("wow_enabled")) setWowOn(true);
    revealVoidZones();
    renderExpansionRadar();
    var snap = window.__rmcOperatorFleetSnapshot;
    if (snap) {
      if (snap.regional_deltas) showRegionalDeltas(snap.regional_deltas);
      lastSchoolsLive = snap.schools_live;
    }
  }

  document.addEventListener("rmc:globe-ready", wireOnce);
  document.addEventListener("rmc:globe-offline-fallback", wireOnce);
  if (document.readyState !== "loading") wireOnce();
  else document.addEventListener("DOMContentLoaded", wireOnce);

  document.addEventListener("rmc:globe-presence-updated", function (ev) {
    updatePresenceUi((ev.detail && ev.detail.others_viewing) || 0);
  });
})();
