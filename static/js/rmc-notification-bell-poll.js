/*
 * rmc-notification-bell-poll.js — live unread-notification badge (GAP-2).
 *
 * The notification bell badge was server-rendered once at page load and then
 * went stale: a notification arriving while the user sat on a page never
 * surfaced until a full reload. This poller keeps every unread badge live by
 * periodically reading the authenticated unread-count endpoint and updating the
 * badges in place.
 *
 * Design:
 *  - Endpoint + interval come from data attributes on the user-dropdown wrapper
 *    (`data-rmc-unread-endpoint`, `data-rmc-unread-interval`) so the URL is never
 *    hardcoded here — it is reversed server-side from the DRF route.
 *  - Targets every `[data-rmc-unread-badge]` element. Avatar-style badges are
 *    hidden at 0 and revealed when the count rises; pill-style badges always show
 *    the number.
 *  - Polling pauses while the tab is hidden (no wasted requests / battery) and
 *    fires an immediate refresh when the tab regains focus.
 *  - On 401/403 the poller stops permanently for the page (the session ended or
 *    the endpoint is forbidden) rather than hammering it — mirrors the assist
 *    dock's auth-aware realtime behaviour.
 *  - Fully self-guarded: a single init, all network/DOM work wrapped so a failure
 *    can never break the page chrome.
 */
(function () {
  "use strict";

  if (window.__rmcBellPollInit) {
    return;
  }
  window.__rmcBellPollInit = true;

  var DEFAULT_INTERVAL_SECONDS = 60;
  var MIN_INTERVAL_SECONDS = 15;
  var MAX_DISPLAY = 99;

  function config() {
    var host = document.querySelector("[data-rmc-unread-endpoint]");
    if (!host) {
      return null;
    }
    var url = host.getAttribute("data-rmc-unread-endpoint");
    if (!url) {
      return null;
    }
    var seconds = parseInt(host.getAttribute("data-rmc-unread-interval"), 10);
    if (!seconds || seconds < MIN_INTERVAL_SECONDS) {
      seconds = DEFAULT_INTERVAL_SECONDS;
    }
    return { url: url, intervalMs: seconds * 1000 };
  }

  function applyCount(count) {
    var badges = document.querySelectorAll("[data-rmc-unread-badge]");
    var text = count > MAX_DISPLAY ? MAX_DISPLAY + "+" : String(count);
    for (var i = 0; i < badges.length; i++) {
      var badge = badges[i];
      var style = badge.getAttribute("data-rmc-unread-badge-style") || "avatar";
      if (style === "avatar") {
        // Reveal only when there is something to show.
        if (count > 0) {
          badge.textContent = text;
          badge.removeAttribute("hidden");
        } else {
          badge.textContent = "";
          badge.setAttribute("hidden", "hidden");
        }
      } else {
        // Pill / menu badge: always present, just reflect the number.
        badge.textContent = text;
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

  function fetchCount() {
    if (state.stopped || !state.cfg) {
      return;
    }
    if (document.hidden) {
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
          // Session ended / forbidden — stop, don't spam.
          stop();
          return null;
        }
        if (!resp.ok) {
          return null;
        }
        return resp.json();
      })
      .then(function (data) {
        if (!data) {
          return;
        }
        var count = parseInt(data.unread_count, 10);
        if (isNaN(count) || count < 0) {
          return;
        }
        try {
          applyCount(count);
        } catch (e) {
          /* never break the chrome on a DOM hiccup */
        }
      })
      .catch(function () {
        /* transient network error — try again next tick */
      });
  }

  function start() {
    state.cfg = config();
    if (!state.cfg) {
      return;
    }
    // Immediate refresh so the badge is accurate within a second of load, then
    // on the configured cadence.
    fetchCount();
    state.timer = window.setInterval(fetchCount, state.cfg.intervalMs);

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !state.stopped) {
        fetchCount();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
