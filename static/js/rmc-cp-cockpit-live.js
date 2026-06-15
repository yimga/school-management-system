/**
 * Poll /super/api/cockpit/live.json and patch pulse + heatmap + header ticker.
 */
(function () {
  "use strict";

  var DEFAULT_POLL_MS = 15000;
  var ENDPOINT = "/super/api/cockpit/live.json";

  function heatmapClassForStatus(status) {
    var raw = String(status || "idle");
    var rmcTier = raw;
    if (raw === "warn") rmcTier = "watch";
    else if (raw === "danger") rmcTier = "critical";
    return {
      lx: "lx-heatmap__tile lx-heatmap__tile--" + raw,
      rmc: "rmc-heatmap__tile rmc-heatmap__tile--" + rmcTier,
    };
  }

  function patchPulse(cards) {
    if (!cards || !cards.length) return;
    var nodes = document.querySelectorAll("[data-rmc-cp-pulse-drill]");
    for (var i = 0; i < nodes.length && i < cards.length; i++) {
      var card = cards[i];
      var el = nodes[i];
      var valueEl = el.querySelector(".rmc-cockpit-pulse-card__value");
      var labelEl = el.querySelector(".rmc-cockpit-pulse-card__label");
      var deltaEl = el.querySelector(".rmc-cockpit-pulse-card__delta");
      var dotEl = el.querySelector(".rmc-cockpit-pulse-card__dot");
      if (valueEl && card.value != null) valueEl.textContent = String(card.value);
      if (labelEl && card.label) labelEl.textContent = String(card.label);
      if (dotEl && card.severity) {
        dotEl.className = "rmc-cockpit-pulse-card__dot rmc-cockpit-pulse-card__dot--" + card.severity;
      }
      if (deltaEl) {
        if (card.delta) {
          deltaEl.textContent = String(card.delta);
          deltaEl.hidden = false;
        } else {
          deltaEl.textContent = "";
          deltaEl.hidden = true;
        }
      }
      el.setAttribute("aria-label", (card.head || "") + ": " + (card.value != null ? card.value : "—"));
    }
    var stamp = document.querySelector("[data-rmc-cp-pulse-refreshed]");
    if (stamp) {
      try {
        stamp.textContent = new Date().toLocaleTimeString();
      } catch (_) { /* noop */ }
    }
  }

  function patchHeatmapMeta(metaText) {
    if (!metaText) return;
    var meta = document.querySelector(".lx-heatmap .lx-card__meta");
    if (meta) meta.textContent = metaText;
  }

  function buildHeatmapTile(tile) {
    var status = tile.status || tile.health_status || "idle";
    var classes = heatmapClassForStatus(status);
    var node = document.createElement("div");
    node.className = classes.lx + " " + classes.rmc;
    node.setAttribute("role", "listitem");
    node.setAttribute("tabindex", "0");
    node.setAttribute("data-label", tile.label || "");
    node.setAttribute("data-rmc-tooltip-text", tile.tooltip || tile.label || "");
    node.setAttribute("data-rmc-heatmap-tooltip", tile.tooltip || tile.label || "");
    if (tile.cell_value) node.setAttribute("data-cell-value", tile.cell_value);
    if (tile.cell_secondary) node.setAttribute("data-cell-secondary", tile.cell_secondary);
    if (tile.tenant_slug) node.setAttribute("data-tenant-slug", tile.tenant_slug);
    if (tile.school_id) node.setAttribute("data-school-id", tile.school_id);
    node.setAttribute("title", tile.tooltip || tile.label || "");
    node.setAttribute("aria-label", tile.tooltip || tile.label || "");
    return node;
  }

  function patchHeatmapTiles(tiles) {
    if (!tiles || !tiles.length) return;
    var grid = document.querySelector(".lx-heatmap__grid[data-rmc-heatmap-grid]");
    if (!grid) return;

    var existing = grid.querySelectorAll(".lx-heatmap__tile");
    if (existing.length !== tiles.length) {
      grid.innerHTML = "";
      for (var n = 0; n < tiles.length; n++) {
        grid.appendChild(buildHeatmapTile(tiles[n]));
      }
      return;
    }

    for (var i = 0; i < tiles.length; i++) {
      var tile = tiles[i];
      var node = existing[i];
      if (!node || !tile) continue;
      var status = tile.status || tile.health_status || "idle";
      var classes = heatmapClassForStatus(status);
      node.className = classes.lx + " " + classes.rmc;
      node.setAttribute("data-label", tile.label || "");
      node.setAttribute("title", tile.tooltip || tile.label || "");
      node.setAttribute("aria-label", tile.tooltip || tile.label || "");
      if (tile.cell_value) node.setAttribute("data-cell-value", tile.cell_value);
      if (tile.cell_secondary) node.setAttribute("data-cell-secondary", tile.cell_secondary);
    }
  }

  function patchFleetLegend(summary) {
    if (!summary) return;
    var legend = document.querySelector(".lx-heatmap__legend[data-rmc-fleet-legend]");
    if (!legend) return;
    var map = [
      ["healthy", summary.healthy || 0],
      ["okay", summary.okay || 0],
      ["warn", summary.warn || 0],
      ["danger", summary.danger || 0],
      ["idle", summary.idle || 0],
    ];
    for (var i = 0; i < map.length; i++) {
      var key = map[i][0];
      var count = map[i][1];
      var span = legend.querySelector("[data-rmc-fleet-tier='" + key + "']");
      if (span) span.setAttribute("data-rmc-fleet-count", String(count));
    }
  }

  function patchTicker(cards) {
    if (!cards || !cards.length) return;
    var track = document.querySelector(".cp-header .rmc-cockpit-ticker__track");
    if (!track) return;
    function renderOne(card, hidden) {
      var sev = card.severity || "info";
      var icon = card.icon
        ? '<span class="rmc-cockpit-ticker__event-icon" aria-hidden="true">' + card.icon + "</span>"
        : "";
      var time = card.timestamp
        ? '<span class="rmc-cockpit-ticker__event-time">· ' + card.timestamp + "</span>"
        : "";
      return (
        '<span class="rmc-cockpit-ticker__event rmc-cockpit-ticker__event--' +
        sev +
        '"' +
        (hidden ? ' aria-hidden="true"' : "") +
        ">" +
        icon +
        '<span class="rmc-cockpit-ticker__event-text">' +
        String(card.text || "") +
        "</span>" +
        time +
        "</span>"
      );
    }
    var html = "";
    for (var i = 0; i < cards.length; i++) html += renderOne(cards[i], false);
    for (var j = 0; j < cards.length; j++) html += renderOne(cards[j], true);
    track.innerHTML = html;
  }

  function applyPayload(payload) {
    if (!payload) return;
    patchPulse(payload.pulse_cards);
    if (payload.tenant_heatmap) {
      patchHeatmapMeta(payload.tenant_heatmap.meta_text);
      patchHeatmapTiles(payload.tenant_heatmap.tiles);
      patchFleetLegend(payload.tenant_heatmap.fleet_summary);
    }
    if (payload.activity_ticker) patchTicker(payload.activity_ticker.cards);
  }

  function pollOnce(intervalRef) {
    // Error backoff: when the endpoint is failing (e.g. 502 while the web
    // service is restarting / under load), skip an increasing number of ticks
    // rather than hammering it every interval — a tight no-backoff retry loop
    // adds load and can prolong a flapping server. Resets on the first success.
    if (intervalRef && intervalRef._skip > 0) {
      intervalRef._skip -= 1;
      return;
    }
    fetch(ENDPOINT, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("status_" + r.status);
        return r.json();
      })
      .then(function (payload) {
        if (intervalRef) {
          intervalRef._fails = 0;
          intervalRef._skip = 0;
        }
        if (payload && payload.poll_interval_seconds && intervalRef) {
          intervalRef.ms = Math.max(5000, Number(payload.poll_interval_seconds) * 1000);
        }
        applyPayload(payload);
      })
      .catch(function () {
        // SSR snapshot stays visible. Back off: skip up to ~8 ticks of the base
        // interval (caps the retry rate while the endpoint recovers).
        if (intervalRef) {
          intervalRef._fails = (intervalRef._fails || 0) + 1;
          intervalRef._skip = Math.min(intervalRef._fails, 8);
        }
      });
  }

  function boot() {
    var root = document.querySelector("[data-rmc-cp-cockpit-live]");
    if (!root) return;
    var intervalRef = { ms: DEFAULT_POLL_MS, handle: null };
    var lastSseRevision = "";

    pollOnce(intervalRef);
    intervalRef.handle = window.setInterval(function () {
      pollOnce(intervalRef);
    }, intervalRef.ms);

    if (typeof EventSource === "undefined") return;

    var source = new EventSource("/super/api/fleet/stream/", { withCredentials: true });
    source.onmessage = function (event) {
      try {
        var snap = JSON.parse(event.data || "{}");
        if (snap.revision && snap.revision === lastSseRevision) return;
        lastSseRevision = snap.revision || "";
        pollOnce(intervalRef);
      } catch (_) { /* noop */ }
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
