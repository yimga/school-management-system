/*
 * rmc-direct-thread-live.js — live new-message delivery in an open thread (IM-3).
 *
 * Previously an open 1:1 thread stayed frozen until a full reload — a new
 * incoming message simply didn't appear. This poller fetches messages newer than
 * the last one rendered and appends them in place, so the conversation updates
 * live. It is the new-message twin of rmc-direct-thread-receipts.js (which only
 * updates the "Seen" indicator).
 *
 * Safety + design:
 *  - Message body and sender name are written via textContent ONLY — never
 *    innerHTML — so a message can't inject markup/script.
 *  - Endpoint + cadence come from data attributes on the thread scroll zone
 *    (`data-rmc-thread-poll-endpoint`, `data-rmc-thread-poll-interval`); the URL
 *    is reversed server-side, never hardcoded.
 *  - Tracks the highest rendered message id and asks only for newer ones.
 *  - Auto-scrolls to the newest message only when the user was already near the
 *    bottom (doesn't yank them up while they read history).
 *  - Pauses while the tab is hidden; refreshes on focus; stops on 401/403.
 */
(function () {
  "use strict";

  if (window.__rmcThreadLiveInit) {
    return;
  }
  window.__rmcThreadLiveInit = true;

  var DEFAULT_INTERVAL_SECONDS = 12;
  var MIN_INTERVAL_SECONDS = 6;
  var NEAR_BOTTOM_PX = 80;

  var container = document.querySelector("[data-rmc-thread-messages]");

  function config() {
    if (!container) {
      return null;
    }
    var url = container.getAttribute("data-rmc-thread-poll-endpoint");
    if (!url) {
      return null;
    }
    var seconds = parseInt(
      container.getAttribute("data-rmc-thread-poll-interval"),
      10
    );
    if (!seconds || seconds < MIN_INTERVAL_SECONDS) {
      seconds = DEFAULT_INTERVAL_SECONDS;
    }
    return { url: url, intervalMs: seconds * 1000 };
  }

  function highestRenderedId() {
    var nodes = container.querySelectorAll("[data-rmc-thread-msg]");
    var max = 0;
    for (var i = 0; i < nodes.length; i++) {
      var id = parseInt(nodes[i].getAttribute("data-message-id"), 10);
      if (!isNaN(id) && id > max) {
        max = id;
      }
    }
    return max;
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

  function el(tag, className) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    return node;
  }

  // Build a message bubble matching the server-rendered structure. ALL
  // user-controlled text goes through textContent.
  function buildBubble(msg) {
    var row = el(
      "div",
      "mb-3 d-flex " + (msg.mine ? "justify-content-end" : "justify-content-start")
    );
    row.setAttribute("data-rmc-thread-msg", "");
    row.setAttribute("data-message-id", String(msg.id));

    var bubble = el(
      "div",
      "rounded-3 px-3 py-2 " +
        (msg.mine ? "bg-primary text-white" : "bg-light") +
        " max-w-75p"
    );

    var meta = el("div", "small opacity-75");
    var who = (msg.sender_name || "").toString();
    var time = formatTime(msg.created_at);
    meta.textContent = who + (time ? " · " + time : "");

    if (msg.mine) {
      // Receipt span the receipts-poller will reveal when the recipient reads it.
      var receipt = el("span", "ms-1 rmc-msg-receipt");
      receipt.setAttribute("data-rmc-msg-receipt", "");
      receipt.setAttribute("data-message-id", String(msg.id));
      receipt.setAttribute("title", "Seen");
      if (!msg.is_read) {
        receipt.setAttribute("hidden", "hidden");
      }
      var icon = el("i", "bi bi-check2-all");
      icon.setAttribute("aria-hidden", "true");
      var at = el("span");
      at.setAttribute("data-rmc-msg-receipt-at", "");
      receipt.appendChild(icon);
      receipt.appendChild(at);
      meta.appendChild(document.createTextNode(" "));
      meta.appendChild(receipt);
    }
    bubble.appendChild(meta);

    if (msg.body) {
      var body = el("div", "mt-1");
      // Preserve line breaks without innerHTML: split on \n, insert <br>.
      var lines = String(msg.body).split("\n");
      for (var i = 0; i < lines.length; i++) {
        if (i > 0) {
          body.appendChild(document.createElement("br"));
        }
        body.appendChild(document.createTextNode(lines[i]));
      }
      bubble.appendChild(body);
    }

    row.appendChild(bubble);
    return row;
  }

  function nearBottom() {
    return (
      container.scrollHeight - container.scrollTop - container.clientHeight <
      NEAR_BOTTOM_PX
    );
  }

  function removeEmptyState() {
    var empty = container.querySelector(".text-muted.text-center");
    if (empty) {
      empty.remove();
    }
  }

  function append(messages) {
    if (!messages || !messages.length) {
      return;
    }
    var wasNearBottom = nearBottom();
    removeEmptyState();
    for (var i = 0; i < messages.length; i++) {
      // Skip anything already in the DOM (defensive against overlap).
      if (
        container.querySelector(
          '[data-rmc-thread-msg][data-message-id="' + messages[i].id + '"]'
        )
      ) {
        continue;
      }
      container.appendChild(buildBubble(messages[i]));
    }
    if (wasNearBottom) {
      container.scrollTop = container.scrollHeight;
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
    var after = highestRenderedId();
    var req;
    try {
      req = fetch(state.cfg.url + "?after=" + encodeURIComponent(after), {
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
          append(data.messages);
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
