/*
 * rmc-group-thread-live.js — live delivery + live read receipts in an open
 * GROUP thread (IM-5).
 *
 * The group-thread twin of rmc-direct-thread-live.js. Previously an open group
 * thread stayed frozen until a full reload — a new post simply didn't appear,
 * and "Read by N/M" never moved. This poller fetches messages newer than the
 * last one rendered, appends them in place, and refreshes the read-receipt
 * counts on the caller's own messages.
 *
 * Safety + design:
 *  - Message content, author name and attachment names are written via
 *    textContent ONLY — never innerHTML — so a post can't inject markup/script.
 *    Attachment hrefs come straight from the server (reversed URLs).
 *  - Endpoint + cadence come from data attributes on the messages container
 *    (`data-rmc-thread-poll-endpoint`, `data-rmc-thread-poll-interval`); the URL
 *    is reversed server-side, never hardcoded.
 *  - Tracks the highest rendered message id and asks only for newer ones.
 *  - Auto-scrolls to the newest message only when the user was already near the
 *    bottom (doesn't yank them up while they read history).
 *  - Pauses while the tab is hidden; refreshes on focus; stops on 401/403.
 *  - Live-appended messages intentionally carry no edit/delete controls (those
 *    need a CSRF form and appear after the next reload).
 */
(function () {
  "use strict";

  if (window.__rmcGroupThreadLiveInit) {
    return;
  }
  window.__rmcGroupThreadLiveInit = true;

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

  function formatWhen(iso) {
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) {
        return "";
      }
      return (
        d.toLocaleDateString() +
        " " +
        d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      );
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

  // Build a message row matching the server-rendered `.message-item` structure.
  // ALL user-controlled text goes through textContent.
  function buildItem(msg) {
    var row = el("div", "message-item mb-3 p-3 border rounded");
    row.setAttribute("data-rmc-thread-msg", "");
    row.setAttribute("data-message-id", String(msg.id));

    var head = el("div", "d-flex justify-content-between align-items-start mb-2");
    var left = el("div");
    var who = el("strong");
    who.textContent = (msg.author_name || "").toString();
    var when = el("span", "text-muted small ms-2");
    when.textContent = formatWhen(msg.created_at);
    left.appendChild(who);
    left.appendChild(when);
    head.appendChild(left);

    var right = el("div", "d-flex align-items-center gap-2");
    if (msg.edited) {
      var badge = el("span", "badge bg-secondary");
      badge.textContent = "Edited";
      right.appendChild(badge);
    }
    head.appendChild(right);
    row.appendChild(head);

    if (msg.content) {
      var body = el("div", "message-content");
      // Preserve line breaks without innerHTML: split on \n, insert <br>.
      var lines = String(msg.content).split("\n");
      for (var i = 0; i < lines.length; i++) {
        if (i > 0) {
          body.appendChild(document.createElement("br"));
        }
        body.appendChild(document.createTextNode(lines[i]));
      }
      row.appendChild(body);
    }

    if (msg.attachments && msg.attachments.length) {
      var wrap = el("div", "mt-2 d-flex flex-column gap-1");
      for (var j = 0; j < msg.attachments.length; j++) {
        var att = msg.attachments[j];
        if (!att || !att.url) {
          continue;
        }
        var link = el("a", "small d-inline-flex align-items-center gap-1");
        link.setAttribute("href", att.url); // server-reversed URL
        var icon = el("i", "bi bi-paperclip");
        icon.setAttribute("aria-hidden", "true");
        link.appendChild(icon);
        link.appendChild(document.createTextNode(att.name || "attachment"));
        wrap.appendChild(link);
      }
      row.appendChild(wrap);
    }

    return row;
  }

  function nearBottom() {
    return (
      container.scrollHeight - container.scrollTop - container.clientHeight <
      NEAR_BOTTOM_PX
    );
  }

  function removeEmptyState() {
    var empty = container.querySelector("[data-rmc-thread-empty]");
    if (empty) {
      empty.remove();
    }
  }

  function appendMessages(messages) {
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
      container.appendChild(buildItem(messages[i]));
    }
    if (wasNearBottom) {
      container.scrollTop = container.scrollHeight;
    }
  }

  function applyReceipts(receipts) {
    if (!receipts || !receipts.length) {
      return;
    }
    for (var i = 0; i < receipts.length; i++) {
      var r = receipts[i];
      if (!r || r.id == null) {
        continue;
      }
      var host = document.querySelector(
        '[data-rmc-thread-readby][data-message-id="' + r.id + '"]'
      );
      if (!host) {
        continue;
      }
      var countEl = host.querySelector("[data-rmc-readby-count]");
      var totalEl = host.querySelector("[data-rmc-readby-total]");
      if (countEl && r.read_by != null) {
        countEl.textContent = String(r.read_by);
      }
      if (totalEl && r.total != null) {
        totalEl.textContent = String(r.total);
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
        if (!data) {
          return;
        }
        try {
          appendMessages(data.messages);
          applyReceipts(data.receipts);
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
