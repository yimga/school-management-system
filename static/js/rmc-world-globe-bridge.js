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
  var lastAppliedRevision = null;
  var lastOperatorFleetRevision = null;
  var hoverFlyTimer = null;
  var VIEWPORT_KEY = "rmc-globe-viewport";
  var SELECTION_KEY = "rmc-copilot-selection";
  var MAP_SHELL_ID = "rmc-world-globe-map-shell";
  var presenceTimer = null;
  var lastPresenceOthers = 0;
  var llmBriefInflight = false;
  var lastLlmBriefRevision = null;

  function readFleetBootstrap() {
    var el = document.getElementById("rmc-operator-fleet-bootstrap");
    if (!el || !el.textContent) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (_e) {
      return null;
    }
  }

  function hydrateFleetSnapshot() {
    var bootstrap = readFleetBootstrap();
    if (!bootstrap) return window.__rmcOperatorFleetSnapshot || null;
    window.__rmcOperatorFleetSnapshot = bootstrap;
    try {
      document.dispatchEvent(new CustomEvent("rmc:fleet-snapshot", { detail: bootstrap }));
    } catch (_e) {
      /* ignore */
    }
    return bootstrap;
  }

  function parsePayloadFeatures() {
    var payload = parsePayload();
    return (payload && payload.features) || {};
  }

  function featureEnabled(key) {
    var features = parsePayloadFeatures();
    if (Object.prototype.hasOwnProperty.call(features, key)) {
      return !!features[key];
    }
    return true;
  }

  function mapShell() {
    return document.getElementById(MAP_SHELL_ID) || (globeEl && globeEl.closest(".lx-world__map"));
  }

  function saveViewportState() {
    if (!api() || !api().isReady()) return;
    try {
      var pov = api().getPointOfView();
      var markers = api().getVisibleMarkers();
      sessionStorage.setItem(
        VIEWPORT_KEY,
        JSON.stringify({
          lat: pov.lat,
          lng: pov.lng,
          altitude: pov.altitude,
          pins_in_view: markers.length,
          ts: Date.now(),
        })
      );
    } catch (_e) {
      /* private mode */
    }
  }

  function restoreViewportState() {
    try {
      var raw = sessionStorage.getItem(VIEWPORT_KEY);
      if (!raw || !api() || !api().isReady() || !api().flyTo) return;
      var saved = JSON.parse(raw);
      if (!saved || typeof saved.altitude !== "number") return;
      var payload = parsePayload() || {};
      var cam = payload.camera || {};
      var lat = typeof saved.lat === "number" ? saved.lat : cam.lat != null ? cam.lat : 8;
      var lng = typeof saved.lng === "number" ? saved.lng : cam.lng != null ? cam.lng : -5;
      var alt = saved.altitude;
      if (alt < 0.85 || alt > 1.55) alt = cam.altitude != null ? cam.altitude : 1.02;
      api().flyTo({ lat: lat, lng: lng, altitude: alt, ms: 0 });
    } catch (_e) {
      /* ignore */
    }
  }

  function saveSelectionFromMarker(marker) {
    if (!marker) return;
    try {
      sessionStorage.setItem(
        SELECTION_KEY,
        JSON.stringify({
          region: marker.region || "",
          school_id: marker.school_id || "",
          slug: marker.slug || "",
          status: marker.status || "",
          name: marker.name || marker.label || "",
        })
      );
    } catch (_e) {
      /* ignore */
    }
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content && meta.content !== "NOTPROVIDED") return meta.content;
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    m = document.cookie.match(/(?:^|; )rmc_manager_csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    return "";
  }

  function viewportPresenceParams() {
    var region = "";
    try {
      var sel = sessionStorage.getItem(SELECTION_KEY);
      if (sel) region = (JSON.parse(sel).region || "").trim();
    } catch (_e) {
      /* ignore */
    }
    var params = new URLSearchParams();
    if (region) params.set("region", region);
    if (api() && api().isReady()) {
      params.set("pins_in_view", String(api().getVisibleMarkers().length));
      params.set("altitude", String(api().getAltitude()));
    }
    return params;
  }

  function sendGlobePresenceHeartbeat() {
    if (!featureEnabled("globe_presence")) return;
    var endpoints = parsePayloadApi() || {};
    var url = endpoints.operator_fleet_globe_presence || "/super/api/operator/fleet/globe-presence/";
    var params = viewportPresenceParams();
    fetch(url + "?" + params.toString(), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrfToken(),
      },
      body: params.toString(),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("presence_failed");
        return r.json();
      })
      .then(function (data) {
        lastPresenceOthers = typeof data.others_viewing === "number" ? data.others_viewing : 0;
        updateViewportChip(null);
        try {
          document.dispatchEvent(
            new CustomEvent("rmc:globe-presence-updated", { detail: { others_viewing: lastPresenceOthers } })
          );
        } catch (_e) {
          /* ignore */
        }
      })
      .catch(function () {
        /* quiet */
      });
  }

  function startGlobePresence() {
    if (presenceTimer || !featureEnabled("globe_presence")) return;
    sendGlobePresenceHeartbeat();
    presenceTimer = window.setInterval(sendGlobePresenceHeartbeat, 30000);
  }

  function fetchLlmBriefIfNeeded(bundle) {
    if (!featureEnabled("ai_brief") || llmBriefInflight) return;
    if (bundle && bundle.brief_source === "llm") return;
    var rev = (bundle && bundle.operator_fleet_revision) || "";
    if (rev && rev === lastLlmBriefRevision) return;
    var endpoints = parsePayloadApi() || {};
    var ctxUrl = endpoints.operator_fleet_context || "/super/api/operator/fleet/context/";
    var params = viewportPresenceParams();
    llmBriefInflight = true;
    fetch(ctxUrl + "?" + params.toString(), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("context_failed");
        return r.json();
      })
      .then(function (ctx) {
        if (ctx.fleet_brief) renderFleetBrief(ctx.fleet_brief);
        if (ctx.brief_source === "llm" && rev) lastLlmBriefRevision = rev;
      })
      .catch(function () {
        /* rules brief already rendered */
      })
      .finally(function () {
        llmBriefInflight = false;
      });
  }

  function updateViewportChip(bundle) {
    var chip = document.getElementById("rmc-world-globe-viewport-chip");
    var voidEl = document.getElementById("rmc-world-globe-void-viewport");
    if (!chip || !featureEnabled("void_zones")) return;
    if (voidEl) voidEl.hidden = false;
    var visible = null;
    if (api() && api().isReady()) {
      visible = api().getVisibleMarkers().length;
    } else if (bundle && typeof bundle.marker_count === "number") {
      visible = bundle.marker_count;
    }
    var alt = api() && api().isReady() ? api().getAltitude() : null;
    var zoomLabel = alt != null ? (alt < 0.85 ? "close" : alt > 1.4 ? "wide" : "regional") : "explore";
    var base = visible != null ? visible + " in view · " + zoomLabel : "Pan & zoom to explore";
    chip.textContent = base;
    saveViewportState();
  }

  function applyAurora(aurora) {
    var shell = mapShell();
    if (!shell || (!featureEnabled("wow_enabled") && !featureEnabled("void_zones"))) return;
    shell.classList.remove(
      "lx-world__map--aurora-warn",
      "lx-world__map--aurora-good",
      "lx-world__map--aurora-danger"
    );
    var tone = aurora || "good";
    if (tone === "warn") shell.classList.add("lx-world__map--aurora-warn");
    else if (tone === "danger") shell.classList.add("lx-world__map--aurora-danger");
    else shell.classList.add("lx-world__map--aurora-good");
  }

  function renderPulseEvents(events) {
    var wrap = document.getElementById("rmc-world-globe-fleet-pulse");
    var list = document.getElementById("rmc-world-globe-pulse-list");
    if (!wrap || !list || !featureEnabled("fleet_pulse")) return;
    if (!Array.isArray(events) || !events.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    list.innerHTML = "";
    events.slice(0, 3).forEach(function (ev) {
      var row = document.createElement("div");
      row.className = "lx-world__fleet-pulse-item";
      var time = document.createElement("time");
      time.textContent = ev.time_label || "";
      var text = document.createElement("span");
      text.textContent = ev.text || "";
      row.appendChild(time);
      row.appendChild(text);
      list.appendChild(row);
    });
  }

  function renderFleetBrief(brief) {
    var wrap = document.getElementById("rmc-world-globe-ai-brief");
    var headline = document.getElementById("rmc-world-globe-brief-headline");
    var body = document.getElementById("rmc-world-globe-brief-body");
    if (!wrap || !headline || !body || !featureEnabled("ai_brief")) return;
    if (!brief || (!brief.headline && !brief.body)) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    headline.textContent = brief.headline || "";
    body.textContent = brief.body || "";
  }

  function renderWhisperLine(line) {
    var voidEl = document.getElementById("rmc-world-globe-void-whisper");
    var el = document.getElementById("rmc-world-globe-whisper-line");
    if (!el || !featureEnabled("ai_whisper")) return;
    if (voidEl) voidEl.hidden = false;
    el.textContent = line || "Fleet healthy · pan to explore pins";
  }

  function renderSchoolHours(count, regionList) {
    var voidEl = document.getElementById("rmc-world-globe-void-school-hours");
    var text = document.getElementById("rmc-world-globe-school-hours-text");
    if (!text || !featureEnabled("void_zones")) return;
    if (voidEl) voidEl.hidden = false;
    if (typeof regionList === "undefined" && window.__rmcOperatorFleetSnapshot) {
      regionList = window.__rmcOperatorFleetSnapshot.school_hours_regions_list;
    }
    if (typeof count !== "number" || count <= 0) {
      text.textContent = "No regions in school hours";
    } else {
      text.textContent = count + " region" + (count === 1 ? "" : "s") + " in school hours";
    }
    var dayArcText = document.getElementById("rmc-world-globe-day-arc-text");
    if (dayArcText && featureEnabled("day_arc")) {
      if (regionList && regionList.length) {
        dayArcText.textContent = regionList.join(" · ") + " · 08:00–15:00 local";
      } else if (count > 0) {
        dayArcText.textContent = count + " region(s) · 08:00–15:00 local";
      } else {
        dayArcText.textContent = "No regions in school hours";
      }
    }
  }

  function revealAllVoidZones() {
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
    if (featureEnabled("wow_enabled") && section && !section.classList.contains("lx-world--wow-on")) {
      document.dispatchEvent(new CustomEvent("rmc:globe-wow-toggle", { detail: { on: true } }));
    }
  }

  function subsolarLongitudeUtc(date) {
    var d = date || new Date();
    var utcHours = d.getUTCHours() + d.getUTCMinutes() / 60 + d.getUTCSeconds() / 3600;
    return ((12 - utcHours) * 15 + 360) % 360 - 180;
  }

  function wireDayNightTerminator() {
    if (!featureEnabled("day_night_terminator")) return;
    var el = document.getElementById("rmc-world-globe-terminator");
    if (!el || el.__rmcTerminatorWired) return;
    el.__rmcTerminatorWired = true;
    el.hidden = false;
    var tick = function () {
      var lon = subsolarLongitudeUtc(new Date());
      var pct = ((lon + 180) / 360) * 100;
      el.style.setProperty("--rmc-terminator-x", pct.toFixed(2) + "%");
    };
    tick();
    window.setInterval(tick, 60000);
  }

  function tourNarratorOptIn() {
    try {
      if (sessionStorage.getItem("rmc-globe-tour-narrator-optin") === "1") return true;
    } catch (_e) {
      /* ignore */
    }
    var cb = document.getElementById("rmc-world-globe-tour-narrator-optin");
    return !!(cb && cb.checked);
  }

  function fetchTourNarratorLine(detail) {
    if (!featureEnabled("tour_narrator") || !tourNarratorOptIn()) return;
    var endpoints = parsePayloadApi() || {};
    var url = endpoints.operator_fleet_tour_narrator || "/super/api/operator/fleet/tour-narrator/";
    var params = new URLSearchParams();
    if (detail.label) params.set("label", detail.label);
    if (detail.region) params.set("region", detail.region);
    if (detail.step_index != null) params.set("step", String(detail.step_index));
    if (detail.lat != null) params.set("lat", String(detail.lat));
    if (detail.lng != null) params.set("lng", String(detail.lng));
    params.set("narrator", "1");
    fetch(url + "?" + params.toString(), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("narrator_failed");
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.line) return;
        var caption = document.getElementById("rmc-world-globe-tour-caption");
        var voidCaption = document.getElementById("rmc-world-globe-void-caption-text");
        if (caption) caption.textContent = data.line;
        if (voidCaption) voidCaption.textContent = data.line;
        announce(data.line);
      })
      .catch(function () {
        /* rules caption already set by mount */
      });
  }

  function wireTourNarrator() {
    if (!featureEnabled("tour_narrator")) return;
    var wrap = document.getElementById("rmc-world-globe-tour-narrator-wrap");
    var cb = document.getElementById("rmc-world-globe-tour-narrator-optin");
    if (wrap) wrap.hidden = false;
    if (cb && !cb.__rmcNarratorWired) {
      cb.__rmcNarratorWired = true;
      try {
        cb.checked = sessionStorage.getItem("rmc-globe-tour-narrator-optin") === "1";
      } catch (_e) {
        /* ignore */
      }
      cb.hidden = false;
      cb.addEventListener("change", function () {
        try {
          sessionStorage.setItem("rmc-globe-tour-narrator-optin", cb.checked ? "1" : "0");
        } catch (_e) {
          /* ignore */
        }
      });
    }
    document.addEventListener("rmc:globe-tour-step", function (ev) {
      fetchTourNarratorLine((ev.detail || {}));
    });
  }

  function buildFleetAskContext() {
    var payload = parsePayload();
    var endpoints = parsePayloadApi() || {};
    var ctx = {
      page_path: window.location.pathname || "",
      page_excerpt: "",
      user_query: "",
      fleet_context: true,
    };
    if (api() && api().isReady()) {
      var markers = api().getVisibleMarkers();
      ctx.pins_in_view = markers.length;
      ctx.altitude = api().getAltitude();
    }
    try {
      var sel = sessionStorage.getItem(SELECTION_KEY);
      if (sel) ctx.selection = JSON.parse(sel);
    } catch (_e) {
      /* ignore */
    }
    var snap = window.__rmcOperatorFleetSnapshot || {};
    ctx.whisper_line = snap.whisper_line || "";
    ctx.operator_fleet_revision = snap.operator_fleet_revision || "";
    ctx.context_url = endpoints.operator_fleet_context || "/super/api/operator/fleet/context/";
    var region = (ctx.selection && ctx.selection.region) || "";
    var schools = snap.schools_live || (payload && payload.markers && payload.markers.length) || "";
    ctx.user_query =
      "Explain the operator fleet globe view. Live schools: " +
      schools +
      ". Suspended: " +
      (snap.suspended || 0) +
      ". Frozen: " +
      (snap.frozen || 0) +
      (region ? ". Focus region: " + region : "") +
      (ctx.pins_in_view != null ? ". Pins in view: " + ctx.pins_in_view : "") +
      ". Suggest next operator actions.";
    ctx.page_excerpt = ctx.user_query;
    return ctx;
  }

  function openFleetAsk(ctx) {
    document.dispatchEvent(new CustomEvent("rmc:fleet-ask", { detail: ctx || buildFleetAskContext() }));
    var input =
      document.querySelector("[data-rmc-copilot-input]") || document.getElementById("aiCopilotInput");
    if (input) {
      input.value = (ctx && ctx.user_query) || buildFleetAskContext().user_query;
      input.focus();
    }
    var rail = document.querySelector("[data-rmc-copilot-rail]");
    if (rail) {
      rail.setAttribute("data-rmc-copilot-active-tab", "chat");
      var shell = document.querySelector(".rmc-app-shell[data-copilot], body[data-copilot]");
      if (shell) shell.setAttribute("data-copilot", "expanded");
    } else {
      var trigger = document.getElementById("aiCopilotTrigger");
      var panel = document.getElementById("aiCopilotPanel");
      if (trigger) trigger.click();
      if (panel) panel.classList.add("active");
    }
    if (window.RMCAssistDock && window.RMCAssistDock.runAIAction) {
      window.RMCAssistDock.runAIAction("fleet_globe_ask", ctx || buildFleetAskContext()).catch(function () {
        /* rules fallback — input already staged */
      });
    }
  }

  function wireAskFleet() {
    var btn = document.getElementById("rmc-world-globe-ask-fleet");
    if (!btn || btn.__rmcAskWired) return;
    btn.__rmcAskWired = true;
    btn.addEventListener("click", function () {
      openFleetAsk(buildFleetAskContext());
    });
  }

  function wireShareViewport() {
    var btn = document.getElementById("rmc-world-globe-share-viewport");
    if (!btn || btn.__rmcShareWired) return;
    btn.__rmcShareWired = true;
    if (!featureEnabled("wow_enabled")) return;
    btn.hidden = false;
    var shareVoid = document.getElementById("rmc-world-globe-void-share");
    if (shareVoid) shareVoid.hidden = false;
    btn.addEventListener("click", function () {
      saveViewportState();
      try {
        var raw = sessionStorage.getItem(VIEWPORT_KEY);
        if (navigator.clipboard && raw) {
          navigator.clipboard.writeText("rmc-globe-view:" + raw).catch(function () {
            /* ignore */
          });
        }
      } catch (_e) {
        /* ignore */
      }
      announce("Viewport saved for this session.");
    });
  }

  function wireGuideCompact() {
    var guide = document.getElementById("rmc-world-globe-operator-guide");
    var toggle = document.getElementById("rmc-world-globe-guide-toggle");
    if (!guide) return;
    var maxSchools = parsePayloadFeatures().compact_guide_max_schools;
    if (maxSchools == null) maxSchools = 5;
    var live = parsePayload();
    var count = live && live.markers ? live.markers.length : 0;
    if (count > maxSchools) return;
    guide.classList.add("lx-world__operator-guide--compact");
    if (toggle) {
      toggle.hidden = false;
      toggle.addEventListener("click", function () {
        guide.classList.toggle("is-expanded");
        toggle.textContent = guide.classList.contains("is-expanded") ? "Hide shortcuts" : "Show shortcuts";
      });
    }
  }

  function applyOperatorFleetChrome(bundle) {
    if (!bundle) return;
    revealAllVoidZones();
    if (Array.isArray(bundle.pulse_events)) renderPulseEvents(bundle.pulse_events);
    renderWhisperLine(bundle.whisper_line || "");
    if (bundle.fleet_brief) renderFleetBrief(bundle.fleet_brief);
    if (bundle.aurora) applyAurora(bundle.aurora);
    renderSchoolHours(
      typeof bundle.school_hours_regions === "number" ? bundle.school_hours_regions : 0,
      bundle.school_hours_regions_list
    );
    updateViewportChip(bundle);
    fetchLlmBriefIfNeeded(bundle);
    startGlobePresence();
    wireAskFleet();
    wireShareViewport();
    if (bundle.pulse_events && bundle.pulse_events.length) {
      var cap = document.getElementById("rmc-world-globe-void-caption-text");
      if (cap && bundle.pulse_events[0].text) {
        cap.textContent = bundle.pulse_events[0].text;
      }
    }
  }

  // Live-refresh circuit breaker (batch: control-plane 502-storm mitigation).
  // The globe is a cosmetic surface; when its live endpoints (/super/api/globe/
  // live + /stream) fail repeatedly — e.g. the web service is 502ing/restarting —
  // a no-backoff 4s-reconnect + 5s-poll loop turns one blip into sustained load
  // that keeps the workers from recovering. After MAX_LIVE_FAILS consecutive
  // failures we open the circuit: stop polling + stop reconnecting + close the
  // stream, and show a quiet "paused" freshness. The circuit resets on a
  // successful refresh or an `online` event, so live updates resume on recovery.
  var liveFails = 0;
  var liveCircuitOpen = false;
  var MAX_LIVE_FAILS = 5;

  function noteLiveSuccess() {
    liveFails = 0;
    liveCircuitOpen = false;
  }

  function openLiveCircuit() {
    if (liveCircuitOpen) return;
    liveCircuitOpen = true;
    stopPollFallback();
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    if (sseReconnectTimer) {
      window.clearTimeout(sseReconnectTimer);
      sseReconnectTimer = null;
    }
    setFreshness("Live paused");
  }

  function noteLiveFailure() {
    liveFails += 1;
    if (liveFails >= MAX_LIVE_FAILS) openLiveCircuit();
  }

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
        if (bundle.revision && bundle.revision !== lastAppliedRevision) {
          countEl.classList.add("lx-world__count--bump");
          window.setTimeout(function () {
            countEl.classList.remove("lx-world__count--bump");
          }, 600);
        }
      }
    }
    if (bundle.revision) lastAppliedRevision = bundle.revision;
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
    applyOperatorFleetChrome(bundle);
    if (typeof bundle.marker_count === "number" && api() && api().isReady()) {
      announce(bundle.marker_count + " schools mapped on globe.");
    }
  }

  function triggerLiveRefresh(force) {
    if (!api() || !api().isReady() || !api().refreshLive) return;
    api()
      .refreshLive(force ? { force: "1" } : {})
      .then(function (bundle) {
        noteLiveSuccess();
        if (bundle) applyLiveChrome(bundle);
      })
      .catch(function () {
        // Server unreachable/erroring — back off via the circuit breaker so the
        // cosmetic globe stops hammering a struggling web service.
        noteLiveFailure();
      });
  }

  function startPollFallback() {
    if (pollTimer || liveCircuitOpen) return;
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
    if (sseReconnectTimer || liveCircuitOpen) return;
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
    saveSelectionFromMarker(marker);
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
        row.classList.add("lx-world__legend-row--active");
        if (api() && api().isReady()) {
          api().highlightRegion(region);
          var flyLat = parseFloat(row.getAttribute("data-rmc-fly-lat"));
          var flyLng = parseFloat(row.getAttribute("data-rmc-fly-lng"));
          var magnetic = featureEnabled("magnetic_fly_to") || featureEnabled("wow_enabled");
          if (magnetic) {
            if (hoverFlyTimer) window.clearTimeout(hoverFlyTimer);
            hoverFlyTimer = window.setTimeout(function () {
              if (!isNaN(flyLat) && !isNaN(flyLng) && api().flyTo) {
                api().flyTo({ lat: flyLat, lng: flyLng, altitude: 1.02, ms: 900 });
              } else if (api().flyToRegion) {
                api().flyToRegion(region, 900);
              }
            }, 420);
          }
        } else highlightSvgRegion(region);
      });
      row.addEventListener("mouseleave", function () {
        row.classList.remove("lx-world__legend-row--active");
        if (hoverFlyTimer) {
          window.clearTimeout(hoverFlyTimer);
          hoverFlyTimer = null;
        }
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
      document.dispatchEvent(
        new CustomEvent("rmc:globe-tour-step", {
          detail: {
            waypoint: wp,
            step_index: (svgTourIndex - 1) % waypoints.length,
            label: (wp && wp.label) || "",
            region: (wp && wp.label) || "",
          },
        })
      );
      svgTourTimer = window.setTimeout(step, wp && wp.dwell_ms ? wp.dwell_ms : 3200);
    };
    step();
  }

  function resetInteraction() {
    stopSvgRegionTour();
    offlineStatusFilter = null;
    highlightSvgRegion(null);
    applySvgStatusFilter(null);
    if (window.RMCGlobeSurface && window.RMCGlobeSurface.hideContextLens) {
      window.RMCGlobeSurface.hideContextLens();
    }
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
      } else if (/^[1-4]$/.test(ev.key) && featureEnabled("void_zones")) {
        var rows = section.querySelectorAll(".lx-world__legend-row[data-rmc-region]");
        var idx = parseInt(ev.key, 10) - 1;
        if (rows[idx]) {
          ev.preventDefault();
          rows[idx].click();
        }
      }
    });
  }

  function wireWowDemoToggle() {
    var btn = document.getElementById("rmc-world-globe-wow-demo");
    if (!btn || btn.__rmcWowDemoWired || !featureEnabled("wow_enabled")) return;
    btn.__rmcWowDemoWired = true;
    btn.hidden = false;
    btn.classList.add("on");
    btn.addEventListener("click", function () {
      var on = !btn.classList.contains("on");
      btn.classList.toggle("on", on);
      document.dispatchEvent(new CustomEvent("rmc:globe-wow-toggle", { detail: { on: on } }));
    });
  }

  function wireMasterLabControls() {
    var lab = document.querySelector("[data-rmc-globe-master-lab]");
    if (!lab || lab.__rmcMasterLabWired) return;
    lab.__rmcMasterLabWired = true;

    var voidToggle = document.getElementById("layer-void");
    var aiToggle = document.getElementById("layer-ai");
    var wowToggle = document.getElementById("layer-wow");
    var wowButton = document.getElementById("toggle-wow");
    var sseButton = document.getElementById("simulate-sse");
    var flyButton = document.getElementById("fly-wa");
    var resetButton = document.getElementById("reset-view");
    var exportButton = document.getElementById("export-snapshot");

    function syncWow(on) {
      lab.classList.toggle("lx-world--wow-on", !!on);
      lab.classList.toggle("lx-world-lab--wow-hidden", !on);
      if (section) {
        section.classList.toggle("lx-world--wow-on", !!on);
      }
      if (wowToggle) wowToggle.checked = !!on;
      if (wowButton) {
        wowButton.classList.toggle("on", !!on);
        wowButton.textContent = on ? "✦ Wow demo ON" : "✦ Wow demo";
      }
      document.dispatchEvent(new CustomEvent("rmc:globe-wow-toggle", { detail: { on: !!on } }));
    }

    function reflectWow(on) {
      lab.classList.toggle("lx-world--wow-on", !!on);
      lab.classList.toggle("lx-world-lab--wow-hidden", !on);
      if (wowToggle) wowToggle.checked = !!on;
      if (wowButton) {
        wowButton.classList.toggle("on", !!on);
        wowButton.textContent = on ? "✦ Wow demo ON" : "✦ Wow demo";
      }
    }

    function syncLayers() {
      lab.classList.toggle("lx-world-lab--void-hidden", voidToggle ? !voidToggle.checked : false);
      lab.classList.toggle("lx-world-lab--ai-hidden", aiToggle ? !aiToggle.checked : false);
      syncWow(wowToggle ? wowToggle.checked : !lab.classList.contains("lx-world-lab--wow-hidden"));
    }

    if (voidToggle) voidToggle.addEventListener("change", syncLayers);
    if (aiToggle) aiToggle.addEventListener("change", syncLayers);
    if (wowToggle) wowToggle.addEventListener("change", syncLayers);
    if (wowButton) {
      wowButton.addEventListener("click", function () {
        syncWow(!(wowToggle ? wowToggle.checked : wowButton.classList.contains("on")));
      });
    }
    if (sseButton) {
      sseButton.addEventListener("click", function () {
        var countEl = section ? section.querySelector(".lx-world__count") : null;
        var current = countEl ? parseInt((countEl.textContent || "").replace(/\D+/g, ""), 10) : 2;
        if (!current || isNaN(current)) current = 2;
        var next = current + 1;
        var bundle = {
          revision: "lab-sse-" + Date.now(),
          operator_fleet_revision: "lab-sse-" + Date.now(),
          schools_live: next,
          marker_count: next,
          display_count: next,
          subline: "Across 2 regions · 1 country today",
          regional_breakdown: [
            { label: "West Africa", count: "1" },
            { label: "Other", count: String(Math.max(1, next - 2)) },
          ],
          pulse_events: [
            { time_label: "now", text: "+1 school live · West Africa" },
            { time_label: "1h", text: "Tour completed · West Africa" },
          ],
          whisper_line: "+1 school live · fleet still 1 suspended",
          school_hours_regions: 1,
          school_hours_regions_list: ["West Africa"],
          aurora: "warn",
          regional_deltas: { "West Africa": 1 },
          fleet_brief: {
            headline: next + " schools, 1 needs eyes.",
            body: "Demo School suspended in Nigeria; New School healthy in Côte d'Ivoire.",
          },
        };
        applyLiveChrome(bundle);
        document.dispatchEvent(new CustomEvent("rmc:globe-live-updated", { detail: { bundle: bundle } }));
        document.dispatchEvent(new CustomEvent("rmc:fleet-snapshot", { detail: bundle }));
        syncWow(true);
      });
    }
    if (flyButton) {
      flyButton.addEventListener("click", function () {
        if (api() && api().isReady()) {
          if (api().flyToRegion) api().flyToRegion("West Africa", 900);
          else if (api().flyTo) api().flyTo({ lat: 8, lng: -5, altitude: 1.02, ms: 900 });
        } else {
          highlightSvgRegion("West Africa");
        }
      });
    }
    if (resetButton) resetButton.addEventListener("click", resetInteraction);
    if (exportButton) {
      exportButton.addEventListener("click", function () {
        var existing = document.getElementById("rmc-world-globe-snapshot-export");
        if (existing) existing.click();
      });
    }
    document.addEventListener("rmc:globe-wow-toggle", function (ev) {
      if (!ev.detail || typeof ev.detail.on !== "boolean") return;
      reflectWow(ev.detail.on);
    });
    syncLayers();
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
        noteLiveSuccess();
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
          } else if (data.pulse_events || data.whisper_line || data.fleet_brief) {
            applyOperatorFleetChrome(data);
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
        noteLiveFailure();
        if (liveCircuitOpen) return;
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
    updateViewportChip(detail.bundle || null);
  });

  document.addEventListener("rmc:fleet-snapshot", function (ev) {
    var detail = ev.detail || {};
    if (!detail.operator_fleet_revision) return;
    if (detail.operator_fleet_revision === lastOperatorFleetRevision && !detail.pulse_events) return;
    lastOperatorFleetRevision = detail.operator_fleet_revision;
    applyOperatorFleetChrome(detail);
    if (detail.globe_revision && detail.globe_revision !== lastStreamRevision) {
      lastStreamRevision = detail.globe_revision;
      triggerLiveRefresh(false);
    }
  });

  function wireBridgeOnce() {
    if (bridgeWired) return;
    bridgeWired = true;
    wireLegendRows();
    wireStatusFilters();
    wireTourControls();
    wireSvgDots();
    applySvgPalette();
    wireAskFleet();
    wireShareViewport();
    wireGuideCompact();
    wireDayNightTerminator();
    wireTourNarrator();
    wireWowDemoToggle();
    wireMasterLabControls();
    revealAllVoidZones();
    applyAurora("good");
    renderWhisperLine("");
    renderSchoolHours(0);
    updateViewportChip(null);
    var snap = hydrateFleetSnapshot() || window.__rmcOperatorFleetSnapshot;
    if (snap) applyOperatorFleetChrome(snap);
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
        window.setInterval(saveViewportState, 4000);
      }
    }
  }

  function bootBridge() {
    wireBridgeOnce();
    syncGlobeModeChrome();
  }

  document.addEventListener("rmc:globe-marker-open", function (ev) {
    var detail = ev.detail || {};
    if (!detail.marker) return;
    if (featureEnabled("context_lens") && window.RMCGlobeSurface && window.RMCGlobeSurface.showContextLens) {
      window.RMCGlobeSurface.showContextLens(detail.marker);
      return;
    }
    renderSheet(detail.marker);
  });

  document.addEventListener("rmc:globe-ready", bootBridge);
  document.addEventListener("rmc:globe-offline-fallback", bootBridge);

  if (typeof window !== "undefined") {
    window.addEventListener("online", function () {
      if (!bridgeWired) return;
      // Back online — clear the live circuit breaker so streams/polls resume.
      noteLiveSuccess();
      syncGlobeModeChrome();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      hydrateFleetSnapshot();
      bootBridge();
    });
  } else {
    hydrateFleetSnapshot();
    bootBridge();
  }
})();
