/*
 * rmc-direct-thread-receipts.js — live "Seen" read receipts (GAP-6).
 *
 * In a 1:1 direct thread the sender previously learned a message had been read
 * only on a full page reload. This poller reads the read-state endpoint for the
 * caller's OWN sent messages and reveals / timestamps the "Seen" receipt in
 * place as soon as the recipient opens the thread.
 *
 * Design mirrors rmc-notification-bell-poll.js:
 *  - Endpoint + cadence come from data attributes on the thread scroll zone
 *    (`data-rmc-thread-receipts-endpoint`, `data-rmc-thread-receipts-interval`),
 *    so the URL is reversed server-side, never hardcoded.
 *  - Pauses while the tab is hidden; refreshes immediately on focus.
 *  - Stops permanently on 401/403; tolerant of transient network errors.
 *  - Only ever reveals receipts that already exist in the DOM (the sender's own
 *    messages), so it can never fabricate a "Seen" state.
 */
(function () {
  "use strict";

  if (window.__rmcThreadReceiptsInit) {
    return;
  }
  window.__rmcThreadReceiptsInit = true;

  var DEFAULT_INTERVAL_SECONDS = 20;
  var MIN_INTERVAL_SECONDS = 10;

  function config() {
    var host = document.querySelector("[data-rmc-thread-receipts-endpoint]");
    if (!host) {
      return null;
    }
    var url = host.getAttribute("data-rmc-thread-receipts-endpoint");
    if (!url) {
      return null;
    }
    var seconds = parseInt(
      host.getAttribute("data-rmc-thread-receipts-interval"),
      10
    );
    if (!seconds || seconds < MIN_INTERVAL_SECONDS) {
      seconds = DEFAULT_INTERVAL_SECONDS;
    }
    return { url: url, intervalMs: seconds * 1000 };
  }

  function formatTime(iso) {
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) {
        return "";
      }
      return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    } catch (e) {
      return "";
    }
  }

  function applyReceipts(rows) {
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!row || row.id == null) {
        continue;
      }
      var el = document.querySelector(
        '[data-rmc-msg-receipt][data-message-id="' + row.id + '"]'
      );
      if (!el) {
        continue;
      }
      el.removeAttribute("hidden");
      var at = el.querySelector("[data-rmc-msg-receipt-at]");
      if (at && row.read_at) {
        var t = formatTime(row.read_at);
        if (t) {
          at.textContent = " " + t;
        }
      }
    }
  }

  var state = { cfg: null, timer: null, stopped: false };

  function stop() {
    state.stopped = true;
    if (state.timer) {
      window.clearInterval(state.timer);
      state.timer = null;
    }
  }

  function poll() {
    if (state.stopped || !state.cfg || document.hidden) {
      return;
    }
    var req;
    try {
      req = fetch(state.cfg.url, {
        method: "GET",
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
      });
    } catch (e) {
      return;
    }
    req
      .then(function (resp) {
        if (resp.status === 401 || resp.status === 403) {
          stop();
          return null;
        }
        if (!resp.ok) {
          return null;
        }
        return resp.json();
      })
      .then(function (data) {
        if (!data || !data.messages) {
          return;
        }
        try {
          applyReceipts(data.messages);
        } catch (e) {
          /* never break the thread on a DOM hiccup */
        }
      })
      .catch(function () {
        /* transient error — retry next tick */
      });
  }

  function start() {
    state.cfg = config();
    if (!state.cfg) {
      return;
    }
    poll();
    state.timer = window.setInterval(poll, state.cfg.intervalMs);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !state.stopped) {
        poll();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
