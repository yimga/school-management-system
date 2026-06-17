/**
 * Tenant-trusted workflow strip — polls tenant-safe active runs (wave 4).
 */
(function () {
  "use strict";

  var ENDPOINT = "/platform-runtime/workflow-progress/tenant-trusted/active/";
  var POLL_MS = 8000;

  function mount() {
    var root = document.querySelector("[data-rmc-wfp-tenant-trust]");
    if (!root) return;

    function paint(runs) {
      if (!runs || !runs.length) {
        root.hidden = true;
        return;
      }
      var body = root.querySelector("[data-rmc-wfp-tenant-trust-body]");
      if (!body) return;
      var parts = [];
      for (var i = 0; i < Math.min(runs.length, 3); i++) {
        var r = runs[i];
        parts.push(
          (r.workflow_label || r.workflow_key) +
            " — " +
            (r.current_step_name || r.status) +
            " (" +
            (r.progress_percent || 0) +
            "%)"
        );
      }
      body.textContent = parts.join(" · ");
      root.hidden = false;
    }

    // Herd-safe poll: self-scheduling with backoff + circuit breaker (the
    // self-inflicted thundering-herd lesson from the /super/ 502 incident). The
    // previous setInterval hammered every 8s forever regardless of response — a
    // 401/403 storm could never stop. Now a 401/403 stops permanently (retrying
    // can never succeed), and transient 5xx/network failures back off
    // exponentially and trip the breaker after a few misses.
    var MAX_MS = 120000;
    var MAX_FAILS = 5;
    var fails = 0;
    var stopped = false;
    var timer = null;

    function schedule(ms) {
      if (stopped) return;
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(poll, ms);
    }

    function poll() {
      if (stopped) return;
      if (document.hidden) {
        schedule(POLL_MS);
        return;
      }
      fetch(ENDPOINT, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          if (r.status === 401 || r.status === 403) {
            stopped = true; // not authorized — retrying can never succeed
            return null;
          }
          if (!r.ok) throw new Error("transient");
          fails = 0;
          return r.json();
        })
        .then(function (data) {
          if (stopped) return;
          if (data && data.runs) paint(data.runs);
          schedule(POLL_MS);
        })
        .catch(function () {
          if (stopped) return;
          fails += 1;
          if (fails >= MAX_FAILS) {
            stopped = true;
            return;
          }
          schedule(Math.min(MAX_MS, POLL_MS * Math.pow(2, fails)));
        });
    }

    poll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
