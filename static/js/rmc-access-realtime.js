/*
 * rmc-access-realtime.js — live refresh when THIS user's RBAC / authority changes.
 *
 * Subscribes to the existing notification WebSocket (NotificationSyncConsumer,
 * "ws/notifications/"). When the server pushes {type:"access_changed"} — emitted by
 * apps.accounts.access_realtime.push_access_changed_realtime whenever the user's
 * AccessRole grants / feature-permissions / Django flags / primary role change — we
 * show a brief toast and soft-reload so nav + permissions re-render without a manual
 * refresh or a re-login.
 *
 * Self-gating: the consumer closes anonymous sockets with code 4401; on that we do
 * not reconnect, so this is inert for logged-out visitors. Listen-only.
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

  var reconnects = 0;
  var reloadScheduled = false;
  var socket = null;

  function wsUrl() {
    var scheme = window.location.protocol === "https:" ? "wss" : "ws";
    return scheme + "://" + window.location.host + "/ws/notifications/";
  }

  function toast(message) {
    try {
      var host = document.querySelector("[data-rmc-toast-host]") || document.body;
      var el = document.createElement("div");
      el.className = "rmc-banner rmc-banner--success";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      el.style.position = "fixed";
      el.style.zIndex = "2147483000";
      el.style.left = "50%";
      el.style.bottom = "24px";
      el.style.transform = "translateX(-50%)";
      el.style.maxWidth = "min(92vw, 480px)";
      el.textContent = message;
      host.appendChild(el);
      window.setTimeout(function () {
        try { el.remove(); } catch (e) { /* noop */ }
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
      try { window.location.reload(); } catch (e) { /* noop */ }
    }, RELOAD_DELAY_MS);
  }

  function onMessage(ev) {
    var data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (data && data.type === "access_changed") {
      toast("Your access was updated — refreshing…");
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
    socket.addEventListener("close", function (ev) {
      // 4401 = unauthenticated socket: stay inert for logged-out visitors.
      if (ev && ev.code === 4401) {
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", connect);
  } else {
    connect();
  }
})();
