/**
 * Poll /super/api/cockpit/live.json and patch pulse + heatmap + header ticker.
 */
(function () {
  "use strict";

  var POLL_MS = 30000;
  var ENDPOINT = "/super/api/cockpit/live.json";

  function logDebug(hypothesisId, message, data) {
    // region agent log
    fetch("http://127.0.0.1:7426/ingest/383483ef-728e-4a6f-8288-6731caa89dc7", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "a48ae2" },
      body: JSON.stringify({
        sessionId: "a48ae2",
        hypothesisId: hypothesisId,
        location: "rmc-cp-cockpit-live.js",
        message: message,
        data: data || {},
        timestamp: Date.now(),
      }),
    }).catch(function () {});
    // endregion
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
      if (valueEl && card.value != null) valueEl.textContent = String(card.value);
      if (labelEl && card.label) labelEl.textContent = String(card.label);
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
    if (stamp && cards.length) {
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

  function patchHeatmapTiles(tiles) {
    if (!tiles || !tiles.length) return;
    var grid = document.querySelector(".lx-heatmap__grid");
    if (!grid) return;
    var existing = grid.querySelectorAll(".lx-heatmap__tile");
    if (existing.length !== tiles.length) return;
    for (var i = 0; i < tiles.length; i++) {
      var tile = tiles[i];
      var node = existing[i];
      if (!node || !tile) continue;
      var status = tile.health_status || tile.status || "idle";
      node.className = "lx-heatmap__tile lx-heatmap__tile--" + status;
      node.setAttribute("title", tile.tooltip || tile.name || "");
      node.setAttribute("aria-label", tile.name || tile.tooltip || "");
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
    }
    if (payload.activity_ticker) patchTicker(payload.activity_ticker.cards);
    logDebug("B", "cockpit_live_applied", {
      generated_at: payload.generated_at,
      pulse: (payload.pulse_cards || []).length,
      heatmap: payload.tenant_heatmap ? payload.tenant_heatmap.total : 0,
    });
  }

  function pollOnce() {
    fetch(ENDPOINT, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("status_" + r.status);
        return r.json();
      })
      .then(applyPayload)
      .catch(function (err) {
        logDebug("B", "cockpit_live_poll_failed", { error: String(err && err.message ? err.message : err) });
      });
  }

  function boot() {
    var root = document.querySelector("[data-rmc-cp-cockpit-live]");
    if (!root) return;
    pollOnce();
    window.setInterval(pollOnce, POLL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
