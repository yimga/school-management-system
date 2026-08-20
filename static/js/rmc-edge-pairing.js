/* Box pairing screen: request a code, then wait to be adopted.
 *
 * This file NEVER handles a credential. The poll response that carries one is
 * consumed server-side by pairing_client.poll(), which writes the binding and
 * returns only a status — so the token never reaches the browser, never lands in
 * a DOM node, and cannot be read out of a screenshot or a devtools panel on a
 * machine sitting in a school office.
 */
(function () {
  "use strict";

  var holder = document.querySelector("[data-rmc-pairing-endpoints]");
  if (!holder) return;

  var startUrl = holder.getAttribute("data-start-url") || "";
  var pollUrl = holder.getAttribute("data-poll-url") || "";
  var statusEl = document.querySelector("[data-rmc-pairing-status]");
  var startBtn = document.querySelector("[data-rmc-pairing-start]");
  var codeEl = document.querySelector("[data-rmc-pairing-code]");
  var timer = null;

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function post(url) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "Content-Type": "application/json" },
      body: "{}"
    }).then(function (r) { return r.json().catch(function () { return {}; }); });
  }

  function say(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function stop() {
    if (timer) { window.clearInterval(timer); timer = null; }
  }

  function handlePoll(data) {
    var status = data && data.status;
    if (status === "paired") {
      stop();
      say("Paired. This box will start syncing on its next cycle.");
      window.setTimeout(function () { window.location.reload(); }, 1500);
      return;
    }
    if (status === "denied") {
      stop();
      say("The request was denied on the cloud.");
      return;
    }
    if (status === "expired") {
      stop();
      say("This code expired before it was approved. Request a new one.");
      return;
    }
    if (status === "unreachable") {
      say("Waiting — the cloud is not reachable right now. Still trying.");
      return;
    }
    if (status === "no_request") {
      stop();
      return;
    }
    say("Waiting for approval…");
  }

  function beginPolling(intervalSeconds) {
    stop();
    var ms = Math.max(3, intervalSeconds || 5) * 1000;
    timer = window.setInterval(function () {
      post(pollUrl).then(handlePoll).catch(function () {
        say("Waiting — the cloud is not reachable right now. Still trying.");
      });
    }, ms);
  }

  if (startBtn) {
    startBtn.addEventListener("click", function () {
      startBtn.disabled = true;
      say("Asking the cloud for a code…");
      post(startUrl).then(function (data) {
        if (data && data.ok) {
          window.location.reload();
          return;
        }
        startBtn.disabled = false;
        say((data && data.message) || "Could not reach the cloud.");
      }).catch(function () {
        startBtn.disabled = false;
        say("Could not reach the cloud.");
      });
    });
  }

  if (codeEl) beginPolling(5);
})();
