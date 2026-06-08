/**
 * Global Footprint bridge — legend fly-to, filters, bottom sheet, SSE freshness (batch 1653).
 * Offline parity (batch 1654): same legend/filter/sheet UX on SVG fallback when WebGL unavailable.
 */
(function () {
  "use strict";
  if (window.__rmcWorldGlobeBridge) return;
  window.__rmcWorldGlobeBridge = true;

  var globeEl = document.getElementById("rmc-world-globe");
  if (!globeEl) return;

  var stageEl =
    document.getElementById("rmc-world-globe-stage") ||
    globeEl.closest(".lx-world__globe-stage") ||
    globeEl.parentElement;
  var section = globeEl.closest(".lx-world");
  var sheetId = "rmc-world-globe-school-sheet";
  var sheetBodyId = "rmc-world-globe-sheet-body";
  var freshnessEl = document.getElementById("rmc-world-globe-freshness");
  var liveRegion = document.getElementById("rmc-world-globe-live-region");
  var eventSource = null;
  var bridgeWired = false;
  var offlineStatusFilter = null;
  var pollTimer = null;
  var sseReconnectTimer = null;
  var lastStreamRevision = null;
  var livePollMs = 5000;
  var sseReconnectMs = 4000;
  var svgTourTimer = null;
  var svgTourIndex = 0;

  function api() {
    return window.RMCWorldGlobe;
  }

  function svgRoot() {
    return stageEl ? stageEl.querySelector(".lx-world__svg-fallback") : null;
  }

  function isOfflineGlobeMode() {
    return (
      (stageEl && stageEl.classList.contains("lx-world__globe--fallback")) ||
      (stageEl && stageEl.getAttribute("data-rmc-globe-mode") === "svg-offline") ||
      !(api() && api().isReady())
    );
  }

  function hideSkeleton() {
    var sk = globeEl.closest(".lx-world__map");
    if (sk) {
      var skeleton = sk.querySelector(".lx-world__globe-skeleton");
      if (skeleton) skeleton.remove();
    }
    if (stageEl) stageEl.classList.add("lx-world__globe--revealed");
  }

  function schoolsListUrl() {
    return globeEl.getAttribute("data-rmc-schools-list-url") || "";
  }

  function parsePayload() {
    var dataEl = document.getElementById("rmc-world-globe-data");
    if (!dataEl || !dataEl.textContent) return null;
    try {
      return JSON.parse(dataEl.textContent);
    } catch (e) {
      return null;
    }
  }

  function parsePayloadApi() {
    var payload = parsePayload();
    return payload && payload.api ? payload.api : null;
  }

  function liveRefreshConfig() {
    var payload = parsePayload();
    return (payload && payload.live_refresh) || {};
  }

  function mergeLiveIntoPayload(bundle) {
    var payload = parsePayload();
    if (!payload || !bundle) return payload;
    if (Array.isArray(bundle.markers)) payload.markers = bundle.markers;
    if (Array.isArray(bundle.country_labels)) payload.country_labels = bundle.country_labels;
    if (Array.isArray(bundle.region_labels)) payload.region_labels = bundle.region_labels;
    if (Array.isArray(bundle.tour_waypoints)) payload.tour_waypoints = bundle.tour_waypoints;
    var el = document.getElementById("rmc-world-globe-data");
    if (el) el.textContent = JSON.stringify(payload);
    return payload;
  }

  function syncSvgLabelsFromBundle(bundle) {
    var svg = svgRoot();
    if (!svg || !bundle) return;
    if (Array.isArray(bundle.region_labels)) {
      bundle.region_labels.forEach(function (row) {
        if (!row || !row.region) return;
        var el = svg.querySelector('.lx-world__svg-region-label[data-rmc-region="' + row.region + '"]');
        if (el && row.text) el.textContent = row.text;
        if (el && row.color) el.setAttribute("fill", row.color);
      });
    }
    if (Array.isArray(bundle.country_labels)) {
      var group = svg.querySelector(".lx-world__svg-country-labels");
      if (!group) return;
      bundle.country_labels.forEach(function (row) {
        if (!row || !row.country_code) return;
        var el = group.querySelector('[data-rmc-country="' + row.country_code + '"]');
        if (!el) {
          el = document.createElementNS("http://www.w3.org/2000/svg", "text");
          el.setAttribute("class", "lx-world__svg-country-label");
          el.setAttribute("data-rmc-region", row.region || "");
          el.setAttribute("data-rmc-country", row.country_code);
          el.setAttribute("text-anchor", "middle");
          group.appendChild(el);
        }
        if (row.svg_x != null) el.setAttribute("x", row.svg_x);
        if (row.svg_y != null) el.setAttribute("y", row.svg_y);
        if (row.text) el.textContent = row.text;
        if (row.color) el.setAttribute("fill", row.color);
      });
    }
  }

  function applyLiveChrome(bundle) {
    if (!bundle || !section) return;
    mergeLiveIntoPayload(bundle);
    syncSvgLabelsFromBundle(bundle);
    if (typeof bundle.schools_live === "number") {
      var countEl = section.querySelector(".lx-world__count");
      if (countEl) {
        var suffix = countEl.querySelector(".lx-world__count-suffix");
        countEl.childNodes[0].textContent = String(bundle.schools_live) + " ";
        if (suffix) countEl.appendChild(suffix);
      }
    }
    if (bundle.subline) {
      var subEl = section.querySelector(".lx-world__count-sub");
      if (subEl) subEl.textContent = bundle.subline;
    }
    if (Array.isArray(bundle.regional_breakdown)) {
      bundle.regional_breakdown.forEach(function (row) {
        var legendRow = section.querySelector('[data-rmc-region="' + row.label + '"].lx-world__legend-row');
        if (!legendRow) return;
        var strong = legendRow.querySelector("strong");
        if (strong) strong.textContent = String(row.count);
        if (row.label_color) {
          legendRow.setAttribute("data-rmc-label-color", row.label_color);
        }
      });
    }
    if (typeof bundle.marker_count === "number" && api() && api().isReady()) {
      announce(bundle.marker_count + " schools mapped on globe.");
    }
  }

  function triggerLiveRefresh(force) {
    if (!api() || !api().isReady() || !api().refreshLive) return;
    api()
      .refreshLive(force ? { force: "1" } : {})
      .then(function (bundle) {
        if (bundle) applyLiveChrome(bundle);
      })
      .catch(function () {
        /* network blip */
      });
  }

  function startPollFallback() {
    if (pollTimer) return;
    var cfg = liveRefreshConfig();
    var ms = cfg.poll_interval_ms || livePollMs;
    pollTimer = window.setInterval(function () {
      triggerLiveRefresh(false);
    }, ms);
  }

  function stopPollFallback() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function scheduleSseReconnect() {
    if (sseReconnectTimer) return;
    var cfg = liveRefreshConfig();
    var ms = cfg.sse_reconnect_ms || sseReconnectMs;
    sseReconnectTimer = window.setTimeout(function () {
      sseReconnectTimer = null;
      connectStream();
    }, ms);
  }

  function setFreshness(text) {
    if (freshnessEl) {
      freshnessEl.textContent = text;
      freshnessEl.classList.toggle("lx-world__freshness--live", text.indexOf("Live") === 0 || text.indexOf("Updated") === 0);
    }
  }

  function announce(text) {
    if (liveRegion) liveRegion.textContent = text;
  }

  function renderSheet(marker) {
    var body = document.getElementById(sheetBodyId);
    if (!body) return;

    if (marker.is_cluster && marker.cluster_members && marker.cluster_members.length) {
      var html = '<ul class="lx-world__sheet-list" data-rmc-scroll-policy="paginate">';
      marker.cluster_members.forEach(function (m) {
        var label = m.name || m.slug || m.school_id || "School";
        html += "<li><span>" + label + "</span><small>" + (m.status || "") + "</small></li>";
      });
      html += "</ul>";
      if (marker.cluster_count > marker.cluster_members.length) {
        html += '<p class="lx-world__sheet-more small text-muted">+' + (marker.cluster_count - marker.cluster_members.length) + " more in this cluster</p>";
      }
      body.innerHTML = html;
    } else {
      var placeParts = [];
      if (marker.city) placeParts.push(marker.city);
      var country = marker.country_name || marker.country_code;
      if (country) placeParts.push(country);
      if (marker.region) placeParts.push(marker.region);
      var place = placeParts.join(" · ");
      body.innerHTML =
        '<div class="lx-world__sheet-single">' +
        "<strong>" + (marker.name || marker.label || "School") + "</strong>" +
        "<p>" + place + "</p>" +
        '<p class="small text-muted">' + (marker.label || marker.status || "") + "</p>" +
        "</div>";
    }

    if (window.RMCSheet && window.RMCSheet.open) {
      window.RMCSheet.open(sheetId);
    } else {
      var dlg = document.getElementById(sheetId);
      if (dlg && dlg.showModal) dlg.showModal();
    }
  }

  function applySvgPalette() {
    var payload = parsePayload();
    if (!payload) return;
    var palette = payload.region_palette || {};
    var svg = svgRoot();
    if (!svg) return;
    svg.querySelectorAll(".lx-world__svg-land[data-rmc-region]").forEach(function (land) {
      var region = land.getAttribute("data-rmc-region");
      var pal = palette[region] || palette.Other;
      if (pal && pal.cap) {
        land.setAttribute("fill", pal.cap);
        land.setAttribute("stroke", pal.side || "rgba(99,102,241,0.22)");
        land.setAttribute("stroke-width", "0.6");
      }
    });
    svg.querySelectorAll(".lx-world__svg-region-label[data-rmc-region]").forEach(function (el) {
      var region = el.getAttribute("data-rmc-region");
      var pal = palette[region] || palette.Other;
      if (pal && pal.label && !el.getAttribute("fill")) {
        el.setAttribute("fill", pal.label);
      }
    });
    svg.querySelectorAll(".lx-world__svg-country-label[data-rmc-region]").forEach(function (el) {
      var region = el.getAttribute("data-rmc-region");
      var pal = palette[region] || palette.Other;
      if (pal && pal.label_country) {
        el.setAttribute("fill", pal.label_country);
      }
    });
  }

  function highlightSvgRegion(region) {
    var svg = svgRoot();
    if (!svg) return;
    var payload = parsePayload();
    var palette = (payload && payload.region_palette) || {};
    svg.querySelectorAll(".lx-world__svg-land[data-rmc-region]").forEach(function (land) {
      var r = land.getAttribute("data-rmc-region");
      var pal = palette[r] || palette.Other || {};
      if (region && r !== region) {
        land.setAttribute("fill", pal.cap_dim || "rgba(40,45,55,0.05)");
        land.style.opacity = "0.55";
      } else if (region && r === region) {
        land.setAttribute("fill", pal.cap_highlight || pal.cap || "rgba(129,140,248,0.22)");
        land.style.opacity = "1";
      } else {
        land.setAttribute("fill", pal.cap || "rgba(148,163,184,0.11)");
        land.style.opacity = "1";
      }
    });
    svg.querySelectorAll(".lx-world__dot-group[data-rmc-region]").forEach(function (el) {
      var r = el.getAttribute("data-rmc-region");
      var dim = region && r !== region;
      el.style.opacity = dim ? "0.28" : "1";
    });
    svg.querySelectorAll(".lx-world__svg-region-label").forEach(function (el) {
      var r = el.getAttribute("data-rmc-region");
      el.classList.toggle("lx-world__svg-region-label--active", region === r);
      el.style.opacity = region && r !== region ? "0.38" : "1";
    });
    svg.querySelectorAll(".lx-world__svg-country-label").forEach(function (el) {
      var r = el.getAttribute("data-rmc-region");
      el.style.opacity = region && r !== region ? "0.35" : "1";
    });
    if (section) {
      section.querySelectorAll("[data-rmc-region]").forEach(function (el) {
        el.classList.toggle("lx-world__legend-row--active", region !== null && el.getAttribute("data-rmc-region") === region);
      });
    }
  }

  function applySvgStatusFilter(status) {
    offlineStatusFilter = status;
    var svg = svgRoot();
    if (!svg) return;
    svg.querySelectorAll(".lx-world__dot-group[data-rmc-status]").forEach(function (el) {
      var st = el.getAttribute("data-rmc-status");
      var hide = status && st !== status;
      el.style.display = hide ? "none" : "";
    });
    if (section) {
      section.querySelectorAll("[data-rmc-status-filter]").forEach(function (el) {
        var val = el.getAttribute("data-rmc-status-filter");
        el.classList.toggle("lx-world__status-chip--active", status !== null && val === status);
        el.setAttribute("aria-pressed", status !== null && val === status ? "true" : "false");
      });
    }
  }

  function findMarkerForDot(dotGroup) {
    var payload = parsePayload();
    if (!payload || !payload.markers) return null;
    var region = dotGroup.getAttribute("data-rmc-region");
    var status = dotGroup.getAttribute("data-rmc-status");
    var country = dotGroup.getAttribute("data-rmc-country");
    for (var i = 0; i < payload.markers.length; i += 1) {
      var m = payload.markers[i];
      if (region && m.region !== region) continue;
      if (status && m.status !== status) continue;
      if (country && m.country_code !== country) continue;
      return m;
    }
    return payload.markers[0] || null;
  }

  function wireSvgDots() {
    var svg = svgRoot();
    if (!svg) return;
    svg.querySelectorAll(".lx-world__dot-group").forEach(function (group) {
      group.setAttribute("tabindex", "0");
      group.setAttribute("role", "button");
      group.style.cursor = "pointer";
      group.addEventListener("click", function () {
        var marker = findMarkerForDot(group);
        if (marker) renderSheet(marker);
      });
      group.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          group.click();
        }
      });
    });
  }

  function wireLegendRows() {
    if (!section) return;
    section.querySelectorAll("[data-rmc-region]").forEach(function (row) {
      var region = row.getAttribute("data-rmc-region");
      if (!region) return;
      row.setAttribute("tabindex", "0");
      row.setAttribute("role", "button");
      row.addEventListener("mouseenter", function () {
        if (api() && api().isReady()) api().highlightRegion(region);
        else highlightSvgRegion(region);
      });
      row.addEventListener("mouseleave", function () {
        if (api() && api().isReady()) api().highlightRegion(null);
        else highlightSvgRegion(null);
      });
      row.addEventListener("click", function () {
        if (api() && api().isReady()) {
          api().flyToRegion(region);
          api().setRegionFilter(null);
        } else {
          highlightSvgRegion(region);
        }
        var listBase = schoolsListUrl();
        if (listBase) {
          var ccMap = { "North America": "US", "West Africa": "NG", "Europe": "GB", "Asia · Oceania": "IN" };
          var cc = ccMap[region];
          if (cc) window.location.assign(listBase + (listBase.indexOf("?") >= 0 ? "&" : "?") + "country_code=" + encodeURIComponent(cc));
        }
      });
      row.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          row.click();
        }
      });
    });
  }

  function wireStatusFilters() {
    if (!section) return;
    section.querySelectorAll("[data-rmc-status-filter]").forEach(function (chip) {
      chip.setAttribute("role", "button");
      chip.setAttribute("tabindex", "0");
      if (!chip.getAttribute("aria-pressed")) chip.setAttribute("aria-pressed", "false");
      chip.addEventListener("click", function () {
        var status = chip.getAttribute("data-rmc-status-filter");
        if (api() && api().isReady()) {
          var active = chip.classList.contains("lx-world__status-chip--active");
          api().setStatusFilter(active ? null : status);
        } else {
          var activeOffline = offlineStatusFilter === status;
          applySvgStatusFilter(activeOffline ? null : status);
        }
      });
      chip.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          chip.click();
        }
      });
    });
  }

  function stopSvgRegionTour() {
    if (svgTourTimer) {
      window.clearTimeout(svgTourTimer);
      svgTourTimer = null;
    }
    svgTourIndex = 0;
    highlightSvgRegion(null);
    var caption = document.getElementById("rmc-world-globe-tour-caption");
    if (caption) caption.textContent = "";
  }

  function startSvgRegionTour() {
    stopSvgRegionTour();
    var payload = parsePayload();
    var waypoints = (payload && payload.tour_waypoints) || [];
    if (!waypoints.length) return;
    var caption = document.getElementById("rmc-world-globe-tour-caption");
    var step = function () {
      var wp = waypoints[svgTourIndex % waypoints.length];
      svgTourIndex += 1;
      if (wp && wp.label) {
        highlightSvgRegion(wp.label);
      }
      if (caption && wp && wp.caption) {
        caption.textContent = wp.caption;
      }
      svgTourTimer = window.setTimeout(step, wp && wp.dwell_ms ? wp.dwell_ms : 3200);
    };
    step();
  }

  function resetInteraction() {
    stopSvgRegionTour();
    offlineStatusFilter = null;
    highlightSvgRegion(null);
    applySvgStatusFilter(null);
    if (api() && api().isReady()) {
      api().resetView();
    }
    announce("Globe view reset.");
  }

  function wireTourControls() {
    var startBtn = document.getElementById("rmc-world-globe-tour-start");
    var stopBtn = document.getElementById("rmc-world-globe-tour-stop");
    var resetBtn = document.getElementById("rmc-world-globe-reset-view");
    if (startBtn) {
      startBtn.addEventListener("click", function () {
        if (api() && api().isReady()) api().startTour();
        else startSvgRegionTour();
      });
    }
    if (stopBtn) {
      stopBtn.addEventListener("click", function () {
        if (api() && api().isReady()) api().stopTour();
        else stopSvgRegionTour();
      });
    }
    if (resetBtn) {
      resetBtn.addEventListener("click", resetInteraction);
    }
    document.addEventListener("keydown", function (ev) {
      var tag = ev.target && ev.target.tagName ? ev.target.tagName.toUpperCase() : "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (!globeEl || !section) return;
      if (ev.key === "r" || ev.key === "R") {
        ev.preventDefault();
        resetInteraction();
      } else if (ev.key === "t" || ev.key === "T") {
        ev.preventDefault();
        if (api() && api().isReady()) api().startTour();
        else startSvgRegionTour();
      } else if (ev.key === "Escape") {
        resetInteraction();
      }
    });
  }

  function connectStream() {
    if (isOfflineGlobeMode()) return;
    var endpoints = parsePayloadApi();
    if (!endpoints || !endpoints.stream || typeof EventSource === "undefined") {
      startPollFallback();
      return;
    }
    if (eventSource) return;
    try {
      eventSource = new EventSource(endpoints.stream);
      eventSource.onopen = function () {
        stopPollFallback();
        setFreshness("Live");
      };
      eventSource.onmessage = function (ev) {
        try {
          var data = JSON.parse(ev.data);
          if (data.ts) {
            setFreshness("Updated " + new Date(data.ts).toLocaleTimeString());
          }
          var revisionChanged = Boolean(data.revision) && data.revision !== lastStreamRevision;
          if (revisionChanged) {
            lastStreamRevision = data.revision;
            triggerLiveRefresh(false);
          } else if (typeof data.schools_live === "number") {
            applyLiveChrome(data);
          }
        } catch (e) {
          /* ignore malformed SSE */
        }
      };
      eventSource.onerror = function () {
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        setFreshness("Reconnecting…");
        startPollFallback();
        scheduleSseReconnect();
      };
    } catch (e) {
      startPollFallback();
    }
  }

  document.addEventListener("rmc:globe-live-updated", function (ev) {
    var detail = ev.detail || {};
    if (detail.bundle) applyLiveChrome(detail.bundle);
  });

  function wireBridgeOnce() {
    if (bridgeWired) return;
    bridgeWired = true;
    wireLegendRows();
    wireStatusFilters();
    wireTourControls();
    wireSvgDots();
    applySvgPalette();
  }

  function syncGlobeModeChrome() {
    hideSkeleton();
    if (isOfflineGlobeMode()) {
      var payload = parsePayload();
      var activeRegion = null;
      if (payload && Array.isArray(payload.markers)) {
        var seen = {};
        payload.markers.forEach(function (m) {
          if (m && m.region) seen[m.region] = true;
        });
        var keys = Object.keys(seen);
        if (keys.length === 1) activeRegion = keys[0];
      }
      if (activeRegion) highlightSvgRegion(activeRegion);
      stopPollFallback();
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      if (sseReconnectTimer) {
        window.clearTimeout(sseReconnectTimer);
        sseReconnectTimer = null;
      }
      setFreshness("Offline map");
      var note = document.getElementById("rmc-world-globe-offline-note");
      if (note) note.hidden = false;
      payload = parsePayload();
      var count = payload && payload.markers ? payload.markers.length : 0;
      announce(count + " schools on regional map (offline).");
    } else {
      stopSvgRegionTour();
      var offlineNote = document.getElementById("rmc-world-globe-offline-note");
      if (offlineNote) offlineNote.hidden = true;
      connectStream();
      setFreshness("Live");
      triggerLiveRefresh(true);
      if (api() && api().isReady()) {
        announce(api().getVisibleMarkers().length + " schools visible on globe.");
      }
    }
  }

  function bootBridge() {
    wireBridgeOnce();
    syncGlobeModeChrome();
  }

  document.addEventListener("rmc:globe-marker-open", function (ev) {
    var detail = ev.detail || {};
    if (detail.marker) renderSheet(detail.marker);
  });

  document.addEventListener("rmc:globe-ready", bootBridge);
  document.addEventListener("rmc:globe-offline-fallback", bootBridge);

  if (typeof window !== "undefined") {
    window.addEventListener("online", function () {
      if (!bridgeWired) return;
      syncGlobeModeChrome();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      if (isOfflineGlobeMode()) bootBridge();
    });
  } else if (isOfflineGlobeMode()) {
    bootBridge();
  }
})();
