/**
 * Operator fleet bus — one SSE/poll stream → CustomEvent('rmc:fleet-snapshot').
 * Loaded on control-plane shell so schools list, tenant health, and globe share revision.
 */
(function () {
  "use strict";
  if (window.__rmcOperatorFleetBus) return;
  window.__rmcOperatorFleetBus = true;

  var SSE_PATH = "/super/api/operator/fleet/stream/";
  var SNAPSHOT_PATH = "/super/api/operator/fleet/snapshot/";
  var eventSource = null;
  var pollTimer = null;
  var reconnectTimer = null;
  var lastRevision = null;
  var POLL_MS = 8000;
  var RECONNECT_MS = 5000;

  function dispatchSnapshot(detail) {
    if (!detail || typeof detail !== "object") return;
    window.__rmcOperatorFleetSnapshot = detail;
    if (detail.operator_fleet_revision) {
      lastRevision = detail.operator_fleet_revision;
    }
    try {
      document.dispatchEvent(
        new CustomEvent("rmc:fleet-snapshot", { detail: detail })
      );
    } catch (_e) {
      /* IE11 guard — not supported on CP */
    }
  }

  function fetchSnapshot() {
    return fetch(SNAPSHOT_PATH, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("snapshot_failed");
        return r.json();
      })
      .then(function (data) {
        dispatchSnapshot(data);
        return data;
      });
  }

  function startPoll() {
    if (pollTimer) return;
    pollTimer = window.setInterval(function () {
      fetchSnapshot().catch(function () {
        /* quiet */
      });
    }, POLL_MS);
  }

  function stopPoll() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = window.setTimeout(function () {
      reconnectTimer = null;
      connectStream();
    }, RECONNECT_MS);
  }

  function connectStream() {
    if (typeof EventSource === "undefined") {
      startPoll();
      fetchSnapshot().catch(function () {
        startPoll();
      });
      return;
    }
    if (eventSource) return;
    try {
      eventSource = new EventSource(SSE_PATH, { withCredentials: true });
      eventSource.onopen = function () {
        stopPoll();
      };
      eventSource.onmessage = function (ev) {
        try {
          var data = JSON.parse(ev.data);
          if (data.transient_error) return;
          var rev = data.operator_fleet_revision;
          if (rev && rev === lastRevision && !data.pulse_events) return;
          dispatchSnapshot(data);
        } catch (_e) {
          /* malformed */
        }
      };
      eventSource.onerror = function () {
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        startPoll();
        scheduleReconnect();
      };
    } catch (_e) {
      startPoll();
    }
  }

  function boot() {
    if (!document.body || document.body.getAttribute("data-rmc-surface") === "marketing") return;
    connectStream();
    fetchSnapshot().catch(function () {
      /* poll loop will retry */
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }

  window.RMCOperatorFleetBus = {
    getSnapshot: function () {
      return window.__rmcOperatorFleetSnapshot || null;
    },
    refresh: function () {
      return fetchSnapshot();
    },
  };
})();
