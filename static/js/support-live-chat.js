/* Customer live support chat widget (Wave 7.4 customer side).
 *
 * Connects to SupportChatConsumer (ws/support/chat/). That consumer is
 * tenant-bound by TenantChannelsMiddleware, so the room is derived server-side
 * from the signed-in user's own (school, user) — the client names no room.
 * Sends messages (each persisted to the user's open support ticket) and renders
 * replies from the support agent. Rendering is broadcast-driven; message text is
 * always written via textContent, never innerHTML. Vanilla JS. */
(function () {
  "use strict";

  var root = document.getElementById("rmc-slc-root");
  if (!root) return;

  var wsPath = root.getAttribute("data-ws-path") || "/ws/support/chat/";
  var myId = root.getAttribute("data-user-id") || "";
  var thread = document.getElementById("rmc-slc-thread");
  var empty = document.getElementById("rmc-slc-empty");
  var composer = document.getElementById("rmc-slc-composer");
  var input = document.getElementById("rmc-slc-input");
  var sendBtn = document.getElementById("rmc-slc-send");
  var statusEl = document.getElementById("rmc-slc-status");

  var ws = null;
  var reconnectDelay = 1000;
  var MAX_RECONNECT = 15000;

  function setStatus(txt) {
    if (statusEl) statusEl.textContent = txt || "";
  }

  function hideEmpty() {
    if (empty) empty.classList.add("rmc-slc-hidden");
  }

  function roleFor(data) {
    if (data.sender_role) return data.sender_role === "agent" ? "agent" : "self";
    return String(data.author_id) === String(myId) ? "self" : "agent";
  }

  function addBubble(role, text) {
    if (!thread) return;
    hideEmpty();
    var wrap = document.createElement("div");
    wrap.className = "rmc-slc-msg rmc-slc-msg--" + (role === "agent" ? "agent" : "self");
    var body = document.createElement("div");
    body.className = "rmc-slc-msg-body";
    body.textContent = text || "";
    var meta = document.createElement("div");
    meta.className = "rmc-slc-msg-meta";
    meta.textContent = role === "agent" ? "Support" : "You";
    wrap.appendChild(body);
    wrap.appendChild(meta);
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;
  }

  function addSystemLine(kind) {
    if (!thread) return;
    hideEmpty();
    var line = document.createElement("div");
    line.className = "rmc-slc-sys";
    line.textContent =
      kind === "resolve"
        ? "Support marked this conversation resolved."
        : kind === "reopen"
        ? "This conversation was reopened."
        : "";
    if (!line.textContent) return;
    thread.appendChild(line);
    thread.scrollTop = thread.scrollHeight;
  }

  function onMessage(ev) {
    var data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (!data || typeof data !== "object") return;
    if (data.type === "history") {
      var msgs = data.messages || [];
      for (var i = 0; i < msgs.length; i++) {
        addBubble(roleFor(msgs[i]), msgs[i].message || "");
      }
      return;
    }
    if (data.type === "chat_message") {
      if (data.sender_role === "system") {
        addSystemLine(data.system);
        return;
      }
      addBubble(roleFor(data), data.message || "");
      return;
    }
    if (data.type === "ack") {
      setStatus("");
      return;
    }
    if (data.error) {
      setStatus("Message could not be sent. Please try again.");
      if (sendBtn) sendBtn.disabled = false;
      return;
    }
  }

  function onSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (!input) return;
    var text = (input.value || "").trim();
    if (!text) return;
    if (!ws || ws.readyState !== 1) {
      setStatus("Reconnecting… your message was not sent.");
      return;
    }
    if (sendBtn) sendBtn.disabled = true;
    ws.send(JSON.stringify({ message: text }));
    input.value = "";
    setStatus("Sending…");
    if (sendBtn) sendBtn.disabled = false;
    input.focus();
  }

  function connect() {
    var scheme = location.protocol === "https:" ? "wss:" : "ws:";
    try {
      ws = new WebSocket(scheme + "//" + location.host + wsPath);
    } catch (e) {
      setStatus("Live chat unavailable.");
      return;
    }
    setStatus("Connecting…");
    ws.onopen = function () {
      setStatus("");
      reconnectDelay = 1000;
      if (input) input.disabled = false;
      if (sendBtn) sendBtn.disabled = false;
    };
    ws.onmessage = onMessage;
    ws.onclose = function () {
      setStatus("Disconnected. Reconnecting…");
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT);
    };
    ws.onerror = function () {
      setStatus("Connection problem.");
    };
  }

  if (composer) composer.addEventListener("submit", onSubmit);
  if (input) {
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        onSubmit(e);
      }
    });
  }
  connect();
})();
