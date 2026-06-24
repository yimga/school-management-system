/**
 * Progressive elevation polish for the Global Footprint globe.
 *
 * The heavy WebGL globe owns physical terrain. This companion keeps the SSR/SVG
 * surface in sync with live fleet intensity so the lab and offline preview do not
 * have a missing enhancement script or a hard 404.
 */
(function () {
  if (window.__rmcWorldGlobeSurfaceElevation) return;
  window.__rmcWorldGlobeSurfaceElevation = true;

  function surfaces() {
    return Array.prototype.slice.call(
      document.querySelectorAll("[data-rmc-globe-surface-elevation]")
    );
  }

  function numberFrom(value, fallback) {
    var parsed = parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function applyElevation(bundle) {
    var data = bundle || {};
    var count = numberFrom(data.schools_live || data.marker_count || data.display_count, 0);
    var level = Math.max(1, Math.min(5, Math.ceil(count / 25)));
    var state = data.aurora || (count > 100 ? "strong" : count > 20 ? "active" : "calm");

    surfaces().forEach(function (surface) {
      surface.classList.add("lx-world--surface-elevated");
      surface.setAttribute("data-rmc-globe-elevation-state", state);
      surface.style.setProperty("--rmc-globe-elevation-level", String(level));
    });
  }

  function readBootstrap() {
    var el = document.getElementById("rmc-operator-fleet-bootstrap");
    if (!el || !el.textContent) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (_err) {
      return null;
    }
  }

  document.addEventListener("rmc:fleet-snapshot", function (ev) {
    applyElevation(ev.detail || {});
  });
  document.addEventListener("rmc:globe-live-updated", function (ev) {
    var detail = ev.detail || {};
    applyElevation(detail.bundle || detail);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      applyElevation(readBootstrap() || {});
    });
  } else {
    applyElevation(readBootstrap() || {});
  }
})();
