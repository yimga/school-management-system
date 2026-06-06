/**
 * Rugged engine network-drop simulator (fiber → blackout).
 *
 * Back-compat: the original behaviour (status label swap, viz hide on blackout,
 * fragment reveal) is preserved for the 5 other surfaces that use the
 * data-mkt-network-state contract. When the richer terminal hooks are present
 * (data-mkt-terminal-log + data-mkt-queue + data-mkt-device), this also drives
 * a 100% client-side local-first capture sim: attendance keeps logging through
 * Degraded / Offline / Blackout (QR + passive RFID), a local sync queue grows
 * while offline and drains on reconnect — no backend call, ever.
 */
(function () {
  "use strict";

  var LABEL_ATTR = {
    fiber: "data-fiber-label",
    degraded: "data-degraded-label",
    offline: "data-offline-label",
    blackout: "data-blackout-label",
    online: "data-online-label",
  };

  function labelFor(statusEl, state) {
    if (!statusEl) return "";
    var attr = LABEL_ATTR[state] || LABEL_ATTR.fiber;
    return statusEl.getAttribute(attr) || "";
  }

  var METHODS = ["RFID", "QR sweep", "RFID", "QR card"];
  var GRADES = ["Grade 4A", "Grade 6B", "Grade 5C", "JSS-2", "Grade 3A", "SSS-1"];
  var CAPTURE_TEXT = {
    fiber: "Capture: QR + passive RFID — synced live, no student phone required",
    degraded: "Capture: QR + RFID — queued on intermittent link",
    offline: "Capture: cardstock QR sweeps — held locally",
    blackout: "Capture: passive RFID taps only — held locally",
  };

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function init(root) {
    var status = root.querySelector("[data-mkt-network-status]");
    var viz = root.querySelector("[data-mkt-network-viz]");
    var fragment = root.querySelector("[data-mkt-network-fragment]");
    var buttons = root.querySelectorAll("[data-mkt-network]");
    var dropSim = root.hasAttribute("data-mkt-drop-simulator");

    // Optional richer-terminal hooks
    var log = root.querySelector("[data-mkt-terminal-log]");
    var queueN = root.querySelector("[data-mkt-queue]");
    var queueWrap = root.querySelector(".mkt-rt-queue");
    var queueNote = root.querySelector("[data-mkt-queue-note]");
    var deviceRich = root.querySelector("[data-mkt-device-rich]");
    var deviceUssd = root.querySelector("[data-mkt-device-ussd]");
    var captureEl = root.querySelector("[data-mkt-capture]");
    var hasTerminal = !!(log && queueN);

    var state = "fiber";
    var queue = 0;
    var synced = 0;
    var seq = 2200;
    var clock = 8 * 3600 + 14 * 60; // 08:14:00 simulated school morning
    var lines = [];

    function hhmmss() {
      var h = Math.floor(clock / 3600) % 24;
      var m = Math.floor((clock % 3600) / 60);
      var s = clock % 60;
      return pad(h) + ":" + pad(m) + ":" + pad(s);
    }

    function pushLine(cls, text) {
      lines.push('<span class="' + cls + '">' + text + "</span>");
      if (lines.length > 8) lines = lines.slice(lines.length - 8);
      log.innerHTML = lines.join("\n");
    }

    function setQueue(n) {
      queue = n;
      queueN.textContent = String(queue);
      if (queueWrap) queueWrap.classList.toggle("is-holding", queue > 0);
      if (queueNote) queueNote.textContent = queue > 0 ? "held offline" : "synced live";
    }

    function setDevice(online) {
      if (deviceRich) deviceRich.hidden = !online;
      if (deviceUssd) deviceUssd.hidden = online;
    }

    function drain() {
      if (queue <= 0) return;
      var n = queue;
      pushLine("drain", "⤢ reconnect — draining " + n + " held event" + (n === 1 ? "" : "s") + "…");
      pushLine("drain", "✓ " + n + " reconciled · 0 conflicts (CRDT merge)");
      synced += n;
      setQueue(0);
    }

    function applyState(next) {
      var offline = next === "offline" || next === "blackout";
      var blackout = next === "blackout";
      var degraded = next === "degraded";
      root.classList.toggle("is-offline", offline);
      root.classList.toggle("is-blackout", blackout);
      root.classList.toggle("is-degraded", degraded);
      if (status) status.textContent = labelFor(status, next) || next;
      if (viz) viz.hidden = blackout;
      if (fragment) fragment.hidden = !blackout && !degraded;

      if (hasTerminal) {
        var online = next === "fiber";
        setDevice(online);
        if (captureEl) captureEl.textContent = CAPTURE_TEXT[next] || CAPTURE_TEXT.fiber;
        // reconnecting to fiber drains everything held
        if (online && queue > 0) drain();
        state = next;
      }
    }

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) {
          b.classList.remove("is-active");
          b.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("is-active");
        btn.setAttribute("aria-pressed", "true");
        var next = btn.getAttribute("data-mkt-network") || "fiber";
        if (!dropSim && next !== "online" && next !== "offline") {
          next = next === "offline" ? "offline" : "fiber";
        }
        applyState(next);
      });
    });

    var active = root.querySelector("[data-mkt-network].is-active");
    applyState(
      active ? active.getAttribute("data-mkt-network") || "fiber" : dropSim ? "fiber" : "online"
    );

    // Live capture loop — only when the terminal is present.
    if (hasTerminal) {
      var tick = function () {
        clock += 3 + (seq % 4); // advance the simulated clock a few seconds
        seq += 1;
        var method = METHODS[seq % METHODS.length];
        var grade = GRADES[seq % GRADES.length];
        var stu = "STU-" + seq;
        var head = hhmmss() + "  " + method + " ▸ " + stu + "  " + grade + "  ";
        if (state === "fiber") {
          synced += 1;
          pushLine("ok", head + "✓ synced");
        } else {
          setQueue(queue + 1);
          pushLine("hold", head + "▣ held locally");
        }
      };
      tick();
      setInterval(tick, 1700);
    }
  }

  document.querySelectorAll("[data-mkt-network-state]").forEach(init);
})();
