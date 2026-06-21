/*
 * rmc-thread-typing.js — generic, cache-backed typing indicator (IM-7).
 *
 * Shared by the 1:1 direct thread and the group thread. Prod is web-only (no
 * WebSocket), so this polls a tiny cache-backed endpoint:
 *   - on textarea input it POSTs a "still typing" ping (throttled);
 *   - every few seconds it GETs the list of other people currently typing and
 *     renders it into the display element.
 *
 * Wiring (data attributes, URLs reversed server-side):
 *   [data-rmc-typing-endpoint]  host carrying the POST/GET URL
 *   [data-rmc-typing-input]     the textarea whose input marks you typing
 *   [data-rmc-typing-display]   where "X is typing…" is shown
 *
 * Safety: names are written via textContent only (never innerHTML). Pauses while
 * the tab is hidden; stops permanently on 401/403.
 */
(function () {
  "use strict";

  if (window.__rmcThreadTypingInit) {
    return;
  }
  window.__rmcThreadTypingInit = true;

  var POLL_MS = 3000;
  var POST_THROTTLE_MS = 2500;

  var host = document.querySelector("[data-rmc-typing-endpoint]");
  var input = document.querySelector("[data-rmc-typing-input]");
  var display = document.querySelector("[data-rmc-typing-display]");
  if (!host || !display) {
    return;
  }
  var url = host.getAttribute("data-rmc-typing-endpoint");
  if (!url) {
    return;
  }

  function csrfToken() {
    var field = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (field && field.value) {
      return field.value;
    }
    var meta = document.querySelector("meta[name=csrf-token]");
    return meta ? meta.getAttribute("content") : "";
  }

  var lastPost = 0;
  var stopped = false;

  function postTyping() {
    if (stopped) {
      return;
    }
    var now = Date.now();
    if (now - lastPost < POST_THROTTLE_MS) {
      return;
    }
    lastPost = now;
    try {
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrfToken(),
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: "",
      })
        .then(function (resp) {
          if (resp.status === 401 || resp.status === 403) {
            stopped = true;
          }
        })
        .catch(function () {});
    } catch (e) {
      /* never break typing on a transient error */
    }
  }

  function render(list) {
    if (!list || !list.length) {
      display.textContent = "";
      display.hidden = true;
      return;
    }
    var names = [];
    for (var i = 0; i < list.length && i < 3; i++) {
      names.push((list[i] && list[i].name) || "Someone");
    }
    var text;
    if (names.length === 1) {
      text = names[0] + " is typing…";
    } else if (names.length === 2) {
      text = names[0] + " and " + names[1] + " are typing…";
    } else {
      text = "Several people are typing…";
    }
    display.textContent = text;
    display.hidden = false;
  }

  function poll() {
    if (stopped || document.hidden) {
      return;
    }
    try {
      fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
      })
        .then(function (resp) {
          if (resp.status === 401 || resp.status === 403) {
            stopped = true;
            return null;
          }
          return resp.ok ? resp.json() : null;
        })
        .then(function (data) {
          if (data) {
            try {
              render(data.typing);
            } catch (e) {
              /* ignore a render hiccup */
            }
          }
        })
        .catch(function () {});
    } catch (e) {
      /* transient error — retry next tick */
    }
  }

  if (input) {
    input.addEventListener("input", postTyping);
  }
  window.setInterval(poll, POLL_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && !stopped) {
      poll();
    }
  });
  poll();
})();
