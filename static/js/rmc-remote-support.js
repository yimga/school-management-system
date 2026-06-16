/* Remote Support — tenant/hub reverse-channel client + consent/request wiring.
 *
 * Polls the cloud for queued operator intents on a herd-safe schedule (circuit
 * breaker after consecutive failures, exponential backoff, visibility-gated —
 * the self-inflicted thundering-herd lesson from the /super/ 502 incident), and
 * sends a connectivity heartbeat so operators can see the tenant is online.
 * Endpoint URLs are read from #rmc-remote-support-config (reverse()'d in Django)
 * so nothing hardcodes a tenant-mount path. Dependency-free, defensive.
 */
(function () {
  "use strict";

  var cfg = document.getElementById("rmc-remote-support-config");
  if (!cfg) return;

  var PLACEHOLDER = "00000000-0000-0000-0000-000000000000";

  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrf(),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body || "",
      credentials: "same-origin",
    });
  }

  function postJSON(url, body) {
    return post(url, body).then(function (r) {
      return r && r.ok ? r.json() : null;
    });
  }

  /* --- consent + request buttons ------------------------------------------ */
  document.addEventListener("click", function (e) {
    var consent = e.target.closest("[data-rmc-remote-support-consent]");
    if (consent) {
      var sid = consent.getAttribute("data-session-id");
      var cUrl = cfg
        .getAttribute("data-consent-url-template")
        .replace(PLACEHOLDER, sid);
      consent.disabled = true;
      post(cUrl).then(function () {
        window.location.reload();
      });
      return;
    }
    var req = e.target.closest("[data-rmc-remote-support-request]");
    if (req) {
      var reason = req.getAttribute("data-reason") || "";
      req.disabled = true;
      post(
        cfg.getAttribute("data-request-url"),
        "reason=" + encodeURIComponent(reason)
      ).then(function () {
        window.location.reload();
      });
    }
  });

  /* --- reverse-channel poll loop (herd-safe) ------------------------------ */
  var BASE_MS = 60000;
  var MAX_MS = 300000;
  var MAX_FAILS = 5;
  var fails = 0;
  var stopped = false;
  var timer = null;

  function applyIntent(intent) {
    try {
      if (intent.kind === "message") {
        var text = (intent.payload && intent.payload.text) || intent.reason || "";
        if (window.RMCNotifyCorner && window.RMCNotifyCorner.show) {
          window.RMCNotifyCorner.show({ title: "Support", message: text });
        }
      } else if (intent.kind === "config_refresh") {
        window.dispatchEvent(new CustomEvent("rmc:config-refresh-requested"));
      } else if (intent.kind === "diagnostic_request") {
        window.dispatchEvent(new CustomEvent("rmc:diagnostic-requested"));
      }
    } catch (err) {
      /* applying an intent must never break the loop */
    }
    var ackUrl = cfg
      .getAttribute("data-ack-url-template")
      .replace(PLACEHOLDER, intent.id);
    post(ackUrl);
  }

  function schedule(ms) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(tick, ms);
  }

  function tick() {
    if (stopped || document.visibilityState !== "visible") return;
    var pendingSync = 0;
    try {
      pendingSync =
        (window.rmcOfflineQueueLength && window.rmcOfflineQueueLength()) || 0;
    } catch (e) {
      pendingSync = 0;
    }
    Promise.all([
      post(cfg.getAttribute("data-heartbeat-url"), "pending_sync=" + pendingSync),
      postJSON(cfg.getAttribute("data-pending-url")),
    ])
      .then(function (res) {
        var data = res[1];
        if (data && data.intents) {
          data.intents.forEach(applyIntent);
        }
        fails = 0;
        schedule(BASE_MS);
      })
      .catch(function () {
        fails += 1;
        if (fails >= MAX_FAILS) {
          stopped = true; // circuit breaker — stop hammering a down server
          return;
        }
        schedule(Math.min(MAX_MS, BASE_MS * Math.pow(2, fails)));
      });
  }

  if (document.visibilityState === "visible") {
    schedule(BASE_MS);
  }
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && !stopped) {
      schedule(2000);
    }
  });
})();
