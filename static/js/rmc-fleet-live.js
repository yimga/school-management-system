/**
 * Live fleet status refresh for operator monitoring tables.
 * SSE heartbeat at /super/api/fleet/stream/ with JSON poll fallback.
 */
(function () {
  "use strict";

  var DEFAULT_POLL_MS = 15000;
  var SSE_ENDPOINT = "/super/api/fleet/stream/";
  var JSON_ENDPOINT = "/super/api/fleet/live.json";

  function tierChipClass(tier) {
    if (tier === "danger") return "table-status-chip--danger";
    if (tier === "warn") return "table-status-chip--warning";
    if (tier === "healthy" || tier === "okay") return "table-status-chip--success";
    return "table-status-chip--muted";
  }

  function cpBadgeClass(tier) {
    if (tier === "danger") return "cp-status-badge-danger";
    if (tier === "warn") return "cp-status-badge-warning";
    if (tier === "healthy" || tier === "okay") return "cp-status-badge-success";
    return "cp-status-badge-inactive";
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

  function patchRegistryRow(row, data) {
    var statusCell = row.querySelector("[data-rmc-fleet-status-cell]");
    if (statusCell) {
      var chip = statusCell.querySelector(".table-status-chip, .cp-status-badge");
      if (chip) {
        chip.className = "table-status-chip " + tierChipClass(data.heatmap_tier);
        chip.textContent = data.fleet_state_label || data.fleet_state || "—";
      }
    }
    var badge = row.querySelector(".cp-registry-fleet-badge");
    if (badge) {
      badge.className = "cp-status-badge cp-registry-fleet-badge " + cpBadgeClass(data.heatmap_tier);
      badge.textContent = data.fleet_state_label || data.fleet_state || "—";
    }
    if (data.roster_state) {
      row.setAttribute("data-state", data.roster_state);
    }
    row.setAttribute("data-rmc-fleet-state", data.fleet_state || "");
    row.setAttribute("data-rmc-fleet-tier", data.heatmap_tier || "");
  }

  function patchRow(row, data) {
    if (!row || !data) return;
    patchRegistryRow(row, data);
    var statusCell = row.querySelector("[data-rmc-fleet-status-cell]");
    if (statusCell) {
      var chip = statusCell.querySelector(".table-status-chip");
      if (chip) {
        chip.className = "table-status-chip " + tierChipClass(data.heatmap_tier);
        chip.textContent = data.fleet_state_label || data.fleet_state || "—";
      }
    }
  }

  function applyPayload(root, payload) {
    if (!payload) return;
    var revision = payload.revision || "";
    if (revision && root.getAttribute("data-rmc-fleet-revision") === revision && !payload.rows) {
      if (payload.summary) {
        patchSummaryBar(root, payload.summary, payload.summary_label);
      }
      return;
    }
    if (revision) root.setAttribute("data-rmc-fleet-revision", revision);

    if (payload.summary || payload.summary_label) {
      patchSummaryBar(root, payload.summary, payload.summary_label);
    }

    if (!payload.rows || !payload.rows.length) return;

    var byId = {};
    for (var i = 0; i < payload.rows.length; i++) {
      byId[payload.rows[i].id] = payload.rows[i];
    }

    var rows = root.querySelectorAll("tr[data-rmc-row-detail][data-school-id]");
    for (var j = 0; j < rows.length; j++) {
      var row = rows[j];
      var id = row.getAttribute("data-school-id");
      if (id && byId[id]) patchRow(row, byId[id]);
    }

    var stamp = root.querySelector("[data-rmc-fleet-refreshed]");
    if (stamp) {
      try {
        stamp.textContent = new Date().toLocaleTimeString();
      } catch (_) { /* noop */ }
    }
  }

  function buildJsonEndpoint(root) {
    var base = root.getAttribute("data-rmc-fleet-live-endpoint") || JSON_ENDPOINT;
    var page = root.getAttribute("data-rmc-fleet-page") || "1";
    var pageSize = root.getAttribute("data-rmc-fleet-page-size") || "50";
    var q = root.getAttribute("data-rmc-fleet-q") || "";
    var sep = base.indexOf("?") >= 0 ? "&" : "?";
    var url = base + sep + "page=" + encodeURIComponent(page) + "&page_size=" + encodeURIComponent(pageSize);
    if (q) url += "&q=" + encodeURIComponent(q);
    return url;
  }

  function pollOnce(root, intervalRef) {
    fetch(buildJsonEndpoint(root), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("status_" + r.status);
        return r.json();
      })
      .then(function (payload) {
        if (payload && payload.poll_interval_seconds && intervalRef) {
          intervalRef.ms = Math.max(5000, Number(payload.poll_interval_seconds) * 1000);
        }
        applyPayload(root, payload);
      })
      .catch(function () { /* keep SSR rows */ });
  }

  function buildStreamEndpoint(root) {
    var base = root.getAttribute("data-rmc-fleet-sse-endpoint") || SSE_ENDPOINT;
    var page = root.getAttribute("data-rmc-fleet-page");
    if (!page) return base;
    var pageSize = root.getAttribute("data-rmc-fleet-page-size") || "50";
    var q = root.getAttribute("data-rmc-fleet-q") || "";
    var sep = base.indexOf("?") >= 0 ? "&" : "?";
    var url =
      base +
      sep +
      "page=" +
      encodeURIComponent(page) +
      "&page_size=" +
      encodeURIComponent(pageSize) +
      "&include_rows=1";
    if (q) url += "&q=" + encodeURIComponent(q);
    return url;
  }

  function bootRoot(root) {
    var intervalRef = { ms: DEFAULT_POLL_MS, handle: null };
    var lastSseRevision = "";

    pollOnce(root, intervalRef);
    intervalRef.handle = window.setInterval(function () {
      pollOnce(root, intervalRef);
    }, intervalRef.ms);

    if (typeof EventSource === "undefined") return;

    var sseUrl = buildStreamEndpoint(root);
    var source = new EventSource(sseUrl, { withCredentials: true });

    source.onmessage = function (event) {
      try {
        var payload = JSON.parse(event.data || "{}");
        var hasRows = payload.rows && payload.rows.length;
        if (payload.revision && payload.revision === lastSseRevision && !hasRows) return;
        lastSseRevision = payload.revision || "";
        applyPayload(root, payload);
        if (!hasRows) {
          pollOnce(root, intervalRef);
        }
      } catch (_) { /* noop */ }
    };

    source.onerror = function () {
      /* poll fallback continues */
    };
  }

  function boot() {
    var roots = document.querySelectorAll("[data-rmc-fleet-live='1']");
    for (var i = 0; i < roots.length; i++) bootRoot(roots[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
