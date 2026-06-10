/**
 * Full-fleet operator wall — chunked SSE bootstrap + fleet-wide row deltas.
 */
(function () {
  "use strict";

  var SSE_ENDPOINT = "/super/api/fleet/stream/";

  function heatmapClasses(tier) {
    var raw = String(tier || "idle");
    var rmcTier = raw;
    if (raw === "warn") rmcTier = "watch";
    else if (raw === "danger") rmcTier = "critical";
    return (
      "lx-heatmap__tile lx-heatmap__tile--" +
      raw +
      " rmc-heatmap__tile rmc-heatmap__tile--" +
      rmcTier +
      " rmc-fleet-wall-tile"
    );
  }

  function patchSummaryBar(root, summary, summaryLabel) {
    var bar = root.querySelector("[data-rmc-fleet-summary-bar]");
    if (!bar) return;
    if (summaryLabel) {
      bar.textContent = summaryLabel;
    } else if (summary) {
      var parts = [];
      if (summary.live) parts.push(summary.live + " live");
      if (summary.watch) parts.push(summary.watch + " watch");
      if (summary.critical) parts.push(summary.critical + " critical");
      if (summary.idle) parts.push(summary.idle + " idle");
      bar.textContent = parts.join(" · ") || summary.total + " total";
    }
  }

  function tenant360Href(schoolId) {
    return "/super/tenants/" + encodeURIComponent(schoolId) + "/360/";
  }

  function buildTile(row) {
    var tier = row.heatmap_tier || "idle";
    var link = document.createElement("a");
    link.href = tenant360Href(row.id);
    link.className = heatmapClasses(tier);
    link.setAttribute("role", "listitem");
    link.setAttribute("tabindex", "0");
    link.setAttribute("data-school-id", row.id);
    link.setAttribute("data-rmc-fleet-tier", tier);
    if (row.row_revision) {
      link.setAttribute("data-rmc-fleet-row-revision", row.row_revision);
    }
    link.setAttribute("data-label", row.name || "");
    var label = (row.tooltip || row.fleet_state_label || row.name || "").trim();
    link.setAttribute("title", label);
    link.setAttribute("aria-label", (row.name || "") + " — " + (row.fleet_state_label || "—"));
    return link;
  }

  function upsertTile(grid, row) {
    if (!grid || !row || !row.id) return;
    var existing = grid.querySelector('[data-school-id="' + row.id + '"]');
    var tier = row.heatmap_tier || "idle";
    if (existing) {
      existing.className = heatmapClasses(tier);
      existing.setAttribute("data-rmc-fleet-tier", tier);
      if (row.row_revision) {
        existing.setAttribute("data-rmc-fleet-row-revision", row.row_revision);
      }
      var label = (row.tooltip || row.fleet_state_label || row.name || "").trim();
      existing.setAttribute("title", label);
      existing.setAttribute("aria-label", (row.name || "") + " — " + (row.fleet_state_label || "—"));
      applyActiveFilter(existing.closest("[data-rmc-fleet-wall='1']"));
      return;
    }
    grid.appendChild(buildTile(row));
    applyActiveFilter(grid.closest("[data-rmc-fleet-wall='1']"));
  }

  function updateCounts(root, loaded, total) {
    var loadedEl = root.querySelector("[data-rmc-fleet-wall-loaded-count]");
    var totalEl = root.querySelector("[data-rmc-fleet-wall-total-count]");
    if (loadedEl && loaded != null) loadedEl.textContent = String(loaded);
    if (totalEl && total != null) totalEl.textContent = String(total);
  }

  function setStatus(root, message) {
    var el = root.querySelector("[data-rmc-fleet-wall-status]");
    if (el) el.textContent = message || "";
  }

  function touchRefreshed(root) {
    var stamp = root.querySelector("[data-rmc-fleet-refreshed]");
    if (stamp) {
      try {
        stamp.textContent = new Date().toLocaleTimeString();
      } catch (_) {
        /* noop */
      }
    }
  }

  function applyActiveFilter(root) {
    if (!root) return;
    var active = root.querySelector("[data-rmc-fleet-wall-filter].active");
    var filter = active ? active.getAttribute("data-rmc-fleet-wall-filter") : "all";
    var tiles = root.querySelectorAll(".rmc-fleet-wall-tile");
    for (var i = 0; i < tiles.length; i++) {
      var tier = tiles[i].getAttribute("data-rmc-fleet-tier") || "idle";
      tiles[i].hidden = filter !== "all" && tier !== filter;
    }
  }

  function wireFilters(root) {
    var buttons = root.querySelectorAll("[data-rmc-fleet-wall-filter]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (event) {
        var btn = event.currentTarget;
        for (var j = 0; j < buttons.length; j++) {
          buttons[j].classList.remove("active");
        }
        btn.classList.add("active");
        applyActiveFilter(root);
      });
    }
  }

  function buildStreamEndpoint(root) {
    var chunkSize = root.getAttribute("data-rmc-fleet-wall-chunk-size") || "50";
    var q = root.getAttribute("data-rmc-fleet-wall-q") || "";
    var url =
      SSE_ENDPOINT +
      "?mode=wall&chunk_size=" +
      encodeURIComponent(chunkSize) +
      "&include_rows=1";
    if (q) url += "&q=" + encodeURIComponent(q);
    return url;
  }

  function handleEvent(root, grid, eventPayload, state) {
    var type = eventPayload.type || "";
    if (type === "unchanged") return;

    if (eventPayload.summary || eventPayload.summary_label) {
      patchSummaryBar(root, eventPayload.summary, eventPayload.summary_label);
    }
    if (eventPayload.total != null) {
      state.total = eventPayload.total;
      updateCounts(root, state.loaded, state.total);
    }

    if (type === "chunk" && eventPayload.rows) {
      for (var i = 0; i < eventPayload.rows.length; i++) {
        upsertTile(grid, eventPayload.rows[i]);
        state.loaded += 1;
      }
      updateCounts(root, state.loaded, state.total);
      setStatus(root, "Loading chunk " + ((eventPayload.chunk_index || 0) + 1) + "/" + (eventPayload.chunk_count || "?"));
    }

    if (type === "wall_ready") {
      setStatus(root, "");
      touchRefreshed(root);
      state.ready = true;
    }

    if (type === "delta" && eventPayload.changed_rows) {
      for (var j = 0; j < eventPayload.changed_rows.length; j++) {
        upsertTile(grid, eventPayload.changed_rows[j]);
      }
      touchRefreshed(root);
    }

    if (type === "summary" && state.ready) {
      touchRefreshed(root);
    }
  }

  function bootRoot(root) {
    var grid = root.querySelector("[data-rmc-fleet-wall-grid]");
    if (!grid) return;

    wireFilters(root);
    applyActiveFilter(root);

    var state = {
      loaded: root.querySelectorAll(".rmc-fleet-wall-tile").length,
      total: Number(
        (root.querySelector("[data-rmc-fleet-wall-total-count]") || {}).textContent || "0"
      ),
      ready: false,
    };
    updateCounts(root, state.loaded, state.total);

    if (typeof EventSource === "undefined") {
      setStatus(root, "Live updates unavailable");
      return;
    }

    var source = new EventSource(buildStreamEndpoint(root), { withCredentials: true });
    source.onmessage = function (event) {
      try {
        handleEvent(root, grid, JSON.parse(event.data || "{}"), state);
      } catch (_) {
        /* noop */
      }
    };
    source.onerror = function () {
      setStatus(root, "Reconnecting…");
    };
  }

  function boot() {
    var roots = document.querySelectorAll("[data-rmc-fleet-wall='1']");
    for (var i = 0; i < roots.length; i++) bootRoot(roots[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
