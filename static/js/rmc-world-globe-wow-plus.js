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
    var wowBtn = document.getElementById("rmc-world-globe-wow-demo");
    if (shareVoid) shareVoid.hidden = !on;
    if (snapBtn && featureEnabled("executive_snapshot")) snapBtn.hidden = false;
    if (wowBtn) wowBtn.classList.toggle("on", !!on);
    if (on) applyAuroraFromSnapshot();
  }

  function applyAuroraFromSnapshot() {
    var snap = window.__rmcOperatorFleetSnapshot || readFleetBootstrap();
    var shell = document.getElementById("rmc-world-globe-map-shell");
    if (!shell || !snap || !snap.aurora) return;
    shell.classList.remove(
      "lx-world__map--aurora-warn",
      "lx-world__map--aurora-good",
      "lx-world__map--aurora-danger"
    );
    if (snap.aurora === "warn") shell.classList.add("lx-world__map--aurora-warn");
    else if (snap.aurora === "danger") shell.classList.add("lx-world__map--aurora-danger");
    else shell.classList.add("lx-world__map--aurora-good");
  }

  function readFleetBootstrap() {
    var el = document.getElementById("rmc-operator-fleet-bootstrap");
    if (!el || !el.textContent) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (_e) {
      return null;
    }
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
      text.textContent = count + " operator" + (count === 1 ? "" : "s") + " viewing";
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
      try {
        if (window.history && window.history.replaceState) {
          window.history.replaceState(null, "", hashEl.textContent);
        }
      } catch (_e) {
        /* ignore */
      }
    } catch (_e) {
      /* ignore */
    }
  }

  function exportExecutiveSnapshot() {
    if (!featureEnabled("executive_snapshot")) return;
    var stage = document.getElementById("rmc-world-globe-stage");
    var canvas = stage ? stage.querySelector("canvas") : null;
    if (!canvas || !canvas.toBlob) return;
    var legend = section.querySelector(".lx-world__legend-panel");
    var mapW = canvas.width;
    var mapH = canvas.height;
    var legW = legend ? Math.round(Math.min(360, mapW * 0.34)) : 0;
    var out = document.createElement("canvas");
    out.width = mapW + legW;
    out.height = mapH;
    var ctx = out.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#0c101c";
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(canvas, 0, 0);
    if (legend && legW) {
      ctx.fillStyle = "#121829";
      ctx.fillRect(mapW, 0, legW, mapH);
      ctx.fillStyle = "#64748b";
      ctx.font = "600 10px Inter, system-ui, sans-serif";
      ctx.fillText("GLOBAL FOOTPRINT", mapW + 16, 28);
      var countEl = section.querySelector(".lx-world__count");
      if (countEl) {
        ctx.fillStyle = "#f1f5f9";
        ctx.font = "700 44px Inter, system-ui, sans-serif";
        var countText = (countEl.childNodes[0] && countEl.childNodes[0].textContent) || countEl.textContent;
        ctx.fillText(String(countText).trim(), mapW + 16, 72);
      }
      var sub = section.querySelector(".lx-world__count-sub");
      if (sub && sub.textContent) {
        ctx.fillStyle = "#94a3b8";
        ctx.font = "12px Inter, system-ui, sans-serif";
        ctx.fillText(sub.textContent.trim().slice(0, 42), mapW + 16, 92);
      }
      var rows = section.querySelectorAll(".lx-world__legend-row[data-rmc-region]");
      rows.forEach(function (row, i) {
        ctx.fillStyle = "#94a3b8";
        ctx.font = "12px Inter, system-ui, sans-serif";
        var label = row.getAttribute("data-rmc-region") || "";
        var strong = row.querySelector("strong");
        var cnt = strong ? strong.textContent : "";
        ctx.fillText(label + "  " + cnt, mapW + 16, 120 + i * 26);
      });
    }
    out.toBlob(function (blob) {
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
    document.addEventListener("rmc:globe-wow-toggle", function (ev) {
      var on = ev.detail && typeof ev.detail.on === "boolean" ? ev.detail.on : true;
      setWowOn(on);
    });

    document.addEventListener("rmc:fleet-snapshot", function (ev) {
      var detail = ev.detail || {};
      if (featureEnabled("wow_enabled") || featureEnabled("void_zones")) setWowOn(true);
      if (detail.regional_deltas) showRegionalDeltas(detail.regional_deltas);
      maybeCelebrateOnboard(detail);
      if (detail.aurora) {
        /* aurora applied by bridge */
      }
      renderExpansionRadar();
      syncShareHash();
    });

    document.addEventListener("rmc:globe-ready", function () {
      setWowOn(featureEnabled("wow_enabled") || featureEnabled("void_zones"));
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
    var bootstrap = readFleetBootstrap();
    if (bootstrap) window.__rmcOperatorFleetSnapshot = bootstrap;
    var wowDefault =
      section.classList.contains("lx-world--wow-on") ||
      featureEnabled("wow_enabled") ||
      featureEnabled("void_zones");
    setWowOn(wowDefault);
    revealVoidZones();
    renderExpansionRadar();
    var snap = window.__rmcOperatorFleetSnapshot;
    if (snap) {
      if (snap.regional_deltas) showRegionalDeltas(snap.regional_deltas);
      lastSchoolsLive = snap.schools_live;
      applyAuroraFromSnapshot();
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
