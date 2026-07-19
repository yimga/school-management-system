/*
 * rmc-substitute-market.js — live refresh on substitute cover-shift market events.
 *
 * Subscribes to SubstituteMarketConsumer at /ws/substitute-market/. When the
 * server pushes {type:"substitute_shift", payload:{event:"shift.open"|…}} —
 * emitted by apps.schoolops.substitute_market open_shift / claim_shift — toast
 * + soft-reload so the open-shifts table updates without a manual refresh.
 *
 * Page-gated: only connects when [data-rmc-substitute-market] is present
 * (ops substitutes hub). Listen-only; 4401/4403 close codes stay inert.
 */
(function () {
  "use strict";
  if (typeof window === "undefined" || !("WebSocket" in window)) {
    return;
  }

  var RECONNECT_MS = 5000;
  var MAX_RECONNECTS = 12;
  var RELOAD_DELAY_MS = 1500;
  var TOAST_MS = 4000;
  var WS_PATH = "/ws/substitute-market/";

  var reconnects = 0;
  var reloadScheduled = false;
  var socket = null;
  var root = null;

  function wsUrl() {
    var scheme = window.location.protocol === "https:" ? "wss" : "ws";
    return scheme + "://" + window.location.host + WS_PATH;
  }

  function msg(key, fallback) {
    if (!root) {
      return fallback;
    }
    return root.getAttribute(key) || fallback;
  }

  function toast(message) {
    try {
      var host = document.querySelector("[data-rmc-toast-host]") || document.body;
      var el = document.createElement("div");
      el.className = "rmc-banner rmc-banner--info";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      el.setAttribute("data-rmc-sub-market-toast", "1");
      el.style.position = "fixed";
      el.style.zIndex = "2147483000";
      el.style.left = "50%";
      el.style.bottom = "24px";
      el.style.transform = "translateX(-50%)";
      el.style.maxWidth = "min(92vw, 480px)";
      el.textContent = message;
      host.appendChild(el);
      window.setTimeout(function () {
        try {
          el.remove();
        } catch (e) {
          /* noop */
        }
      }, TOAST_MS);
    } catch (e) {
      /* toast is best-effort */
    }
  }

  function scheduleReload() {
    if (reloadScheduled) {
      return;
    }
    reloadScheduled = true;
    window.setTimeout(function () {
      try {
        window.location.reload();
      } catch (e) {
        /* noop */
      }
    }, RELOAD_DELAY_MS);
  }

  function onMessage(ev) {
    var data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (!data || data.type !== "substitute_shift") {
      return;
    }
    var payload = data.payload || {};
    var eventName = payload.event || "";
    if (eventName === "shift.open") {
      toast(msg("data-rmc-sub-msg-open", "A cover shift opened — refreshing…"));
      scheduleReload();
      return;
    }
    if (eventName === "shift.claimed") {
      toast(msg("data-rmc-sub-msg-claimed", "A cover shift was claimed — refreshing…"));
      scheduleReload();
    }
  }

  function connect() {
    try {
      socket = new WebSocket(wsUrl());
    } catch (e) {
      return;
    }
    socket.addEventListener("message", onMessage);
    socket.addEventListener("open", function () {
      reconnects = 0;
      if (root) {
        root.setAttribute("data-rmc-sub-market-connected", "1");
      }
    });
    socket.addEventListener("close", function (ev) {
      if (root) {
        root.removeAttribute("data-rmc-sub-market-connected");
      }
      // 4401 unauthenticated / 4403 tenant denied: stay inert.
      if (ev && (ev.code === 4401 || ev.code === 4403)) {
        return;
      }
      if (reloadScheduled) {
        return;
      }
      if (reconnects++ < MAX_RECONNECTS) {
        window.setTimeout(connect, RECONNECT_MS);
      }
    });
  }

  function boot() {
    root = document.querySelector("[data-rmc-substitute-market]");
    if (!root) {
      return;
    }
    connect();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
