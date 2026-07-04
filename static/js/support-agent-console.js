/* Operator live support console client (Wave 7.4 agent side).
 *
 * Connects to SupportAgentConsumer (ws/support/agent/), subscribes to ONE
 * ticket's private (school, user) room at a time, renders the shared customer
 * <-> agent conversation, and posts operator replies. Rendering is purely
 * broadcast-driven (no optimistic append): the agent is a member of the room it
 * posts into, so every message — its own included — paints exactly once when the
 * server echoes it. Vanilla JS, no dependencies. Message text is always written
 * via textContent, never innerHTML, so a customer cannot inject markup. */
(function () {
  "use strict";

  var root = document.getElementById("rmc-sac-root");
  if (!root) return;

  var wsPath = root.getAttribute("data-ws-path") || "/ws/support/agent/";
  var queue = document.getElementById("rmc-sac-queue");
  var thread = document.getElementById("rmc-sac-thread");
  var composer = document.getElementById("rmc-sac-composer");
  var input = document.getElementById("rmc-sac-input");
  var sendBtn = document.getElementById("rmc-sac-send");
  var conn = document.getElementById("rmc-sac-conn");
  var headEmpty = root.querySelector(".rmc-sac-head-empty");
  var headActive = root.querySelector(".rmc-sac-head-active");
  var headSubject = document.getElementById("rmc-sac-head-subject");
  var headMeta = document.getElementById("rmc-sac-head-meta");

  var ws = null;
  var activeTicket = null;
  var reconnectDelay = 1000;
  var MAX_RECONNECT = 15000;

  function setConn(state) {
    if (conn) conn.setAttribute("data-state", state);
  }

  function fmtTime(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (e) {
      return "";
    }
  }

  function addBubble(msg) {
    if (!thread) return;
    var role = msg.sender_role === "customer" ? "customer" : "agent";
    var wrap = document.createElement("div");
    wrap.className = "rmc-sac-msg rmc-sac-msg--" + role;
    var body = document.createElement("div");
    body.className = "rmc-sac-msg-body";
    body.textContent = msg.body != null ? msg.body : (msg.message || "");
    var meta = document.createElement("div");
    meta.className = "rmc-sac-msg-meta";
    var who = role === "customer" ? "Customer" : "You";
    meta.textContent = who + (msg.created_at ? " · " + fmtTime(msg.created_at) : "");
    wrap.appendChild(body);
    wrap.appendChild(meta);
    thread.appendChild(wrap);
    thread.scrollTop = thread.scrollHeight;
  }

  function clearThread() {
    if (thread) thread.textContent = "";
  }

  function enableComposer(on) {
    if (input) input.disabled = !on;
    if (sendBtn) sendBtn.disabled = !on;
  }

  function setActive(ticketId, subject, metaText) {
    activeTicket = ticketId;
    if (headEmpty) headEmpty.classList.add("d-none");
    if (headActive) headActive.classList.remove("d-none");
    if (headSubject) headSubject.textContent = subject || "";
    if (headMeta) headMeta.textContent = metaText || "";
    var items = queue ? queue.querySelectorAll(".rmc-sac-queue-item") : [];
    for (var i = 0; i < items.length; i++) {
      var on = items[i].getAttribute("data-ticket-id") === ticketId;
      items[i].classList.toggle("is-active", on);
      items[i].setAttribute("aria-selected", on ? "true" : "false");
    }
  }

  function subscribe(ticketId) {
    if (!ws || ws.readyState !== 1 || !ticketId) return;
    ws.send(JSON.stringify({ action: "subscribe", ticket_id: ticketId }));
  }

  function onQueueClick(e) {
    var btn = e.target.closest ? e.target.closest(".rmc-sac-queue-item") : null;
    if (!btn) return;
    var ticketId = btn.getAttribute("data-ticket-id");
    var subject = btn.getAttribute("data-subject") || "";
    var school = btn.getAttribute("data-school") || "";
    var user = btn.getAttribute("data-user") || "";
    clearThread();
    setActive(ticketId, subject, [school, user].filter(Boolean).join(" · "));
    subscribe(ticketId);
  }

  function onMessage(ev) {
    var data;
    try {
      data = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    if (!data || typeof data !== "object") return;

    if (data.type === "subscribed") {
      clearThread();
      var hist = data.history || [];
      for (var i = 0; i < hist.length; i++) addBubble(hist[i]);
      if (headSubject && data.subject) headSubject.textContent = data.subject;
      if (headMeta) {
        headMeta.textContent = [data.school_name, data.status]
          .filter(Boolean)
          .join(" · ");
      }
      enableComposer(true);
      if (input) input.focus();
      return;
    }
    if (data.type === "chat_message") {
      if (data.ticket_id && activeTicket && data.ticket_id !== activeTicket) return;
      addBubble(data);
      return;
    }
    if (data.type === "ack") {
      enableComposer(true);
      return;
    }
    if (data.error) {
      enableComposer(true);
      return;
    }
  }

  function onSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (!activeTicket || !input) return;
    var text = (input.value || "").trim();
    if (!text) return;
    if (!ws || ws.readyState !== 1) return;
    if (sendBtn) sendBtn.disabled = true;
    ws.send(JSON.stringify({ action: "message", ticket_id: activeTicket, message: text }));
    input.value = "";
    input.focus();
  }

  function connect() {
    var scheme = location.protocol === "https:" ? "wss:" : "ws:";
    try {
      ws = new WebSocket(scheme + "//" + location.host + wsPath);
    } catch (e) {
      setConn("error");
      return;
    }
    setConn("connecting");
    ws.onopen = function () {
      setConn("online");
      reconnectDelay = 1000;
      if (activeTicket) subscribe(activeTicket);
    };
    ws.onmessage = onMessage;
    ws.onclose = function () {
      setConn("offline");
      enableComposer(false);
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT);
    };
    ws.onerror = function () {
      setConn("error");
    };
  }

  if (queue) queue.addEventListener("click", onQueueClick);
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
