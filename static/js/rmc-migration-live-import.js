/**
 * Migration Cloud kickoff live board.
 * Polls the tenant-scoped bundle progress JSON and paints pipeline / counts /
 * remediator on the Review & Import page. Reloads once when an in-flight apply
 * settles. Hides held / repair chrome the moment issue_count is 0.
 */
(function () {
  "use strict";

  var POLL_MS_ACTIVE = 1200;
  var POLL_MS_SETTLED = 5000;
  var MAX_ACTIVE_TRIES = 240;
  var _maxPercentSeen = 0;

  function board() {
    return (
      document.getElementById("mc-live-board") ||
      document.querySelector("[data-mc-live-board]")
    );
  }

  function seedPayload() {
    var node = document.getElementById("mc-live-import-seed");
    if (!node) return null;
    try {
      return JSON.parse(node.textContent || "null");
    } catch (_err) {
      return null;
    }
  }

  function setText(el, value) {
    if (el) el.textContent = value == null ? "" : String(value);
  }

  function paintPipeline(root, stages) {
    var list = root.querySelector("[data-mc-live-pipeline]");
    if (!list || !stages || !stages.length) return;
    var items = list.querySelectorAll("[data-mc-stage]");
    for (var i = 0; i < items.length; i++) {
      var key = items[i].getAttribute("data-mc-stage");
      var stage = null;
      for (var j = 0; j < stages.length; j++) {
        if (stages[j] && stages[j].key === key) {
          stage = stages[j];
          break;
        }
      }
      if (!stage) continue;
      items[i].className =
        "rmc-wfp-pipeline__stage rmc-wfp-pipeline__stage--" + (stage.visual || "pending");
      var label = items[i].querySelector(".rmc-wfp-pipeline__label");
      if (label && stage.label) label.textContent = stage.label;
    }
  }

  function monotonicPercent(data) {
    var raw = Number(data && data.percent != null ? data.percent : 0);
    if (!isFinite(raw)) raw = 0;
    var rowsProcessed = Number(
      data && data.rows_processed != null ? data.rows_processed : data.processed || 0
    );
    if (data && data.importing) {
      if (
        rowsProcessed === 0 &&
        _maxPercentSeen > 0 &&
        raw + 15 < _maxPercentSeen
      ) {
        _maxPercentSeen = raw;
      }
      if (raw < _maxPercentSeen) raw = _maxPercentSeen;
      else _maxPercentSeen = raw;
    } else if (data && data.succeeded) {
      _maxPercentSeen = 100;
      raw = 100;
    } else {
      _maxPercentSeen = Math.max(_maxPercentSeen, raw);
    }
    return raw;
  }

  function paintCanvas(data) {
    var el = document.querySelector("[data-rmc-wfp-canvas]");
    if (!el || !data) return;
    var fill = el.querySelector("[data-rmc-wfp-fill]");
    var pct = el.querySelector("[data-rmc-wfp-pct]");
    var processed = el.querySelector("[data-rmc-wfp-processed]");
    var expected = el.querySelector("[data-rmc-wfp-expected]");
    var percent = monotonicPercent(data);
    if (fill) fill.style.width = percent.toFixed(2) + "%";
    if (pct) pct.textContent = percent.toFixed(2) + "%";
    var rowsProcessed = data.rows_processed != null ? data.rows_processed : data.processed;
    if (processed) processed.textContent = String(rowsProcessed != null ? rowsProcessed : 0);
    var rowsExpected = data.rows_expected != null ? data.rows_expected : data.expected;
    if (expected) expected.textContent = String(rowsExpected != null ? rowsExpected : 0);
    paintLogTerminal(el, data);
  }

  var _seenLogCount = 0;

  function paintLogTerminal(canvasEl, data) {
    var logHost = canvasEl.querySelector("[data-rmc-wfp-log]");
    if (!logHost || !data) return;
    var lines = data.log_lines || [];
    if (data.importing && lines.length < _seenLogCount) {
      _seenLogCount = 0;
      logHost.innerHTML = "";
    }
    if (lines.length <= _seenLogCount) return;
    for (var i = _seenLogCount; i < lines.length; i++) {
      var line = lines[i];
      if (!line) continue;
      var row = document.createElement("div");
      row.className = "rmc-wfp-log__line";
      row.textContent = line;
      logHost.appendChild(row);
    }
    _seenLogCount = lines.length;
    while (logHost.children.length > 80) {
      logHost.removeChild(logHost.firstChild);
      _seenLogCount = Math.max(0, _seenLogCount - 1);
    }
    logHost.scrollTop = logHost.scrollHeight;
  }

  function paintRemediator(root, remediator) {
    var host = root.querySelector("[data-mc-live-remediator]");
    if (!host) return;
    if (!remediator) {
      host.hidden = true;
      host.innerHTML = "";
      return;
    }
    host.hidden = false;
    var title = host.querySelector("[data-mc-remediator-title]");
    var steps = host.querySelector("[data-mc-remediator-steps]");
    var action = host.querySelector("[data-mc-remediator-action]");
    if (title) title.textContent = remediator.title || "";
    if (steps && remediator.steps && remediator.steps.length) {
      steps.innerHTML = "";
      remediator.steps.forEach(function (line) {
        var li = document.createElement("li");
        li.textContent = line;
        steps.appendChild(li);
      });
    }
    if (action && remediator.action_label) {
      action.textContent = remediator.action_label;
    }
  }

  function paintLastImport(data) {
    var card = document.getElementById("mc-last-import");
    if (!card || !data) return;
    var last = data.last_import || {};
    setText(card.querySelector("[data-mc-last-created]"), last.created != null ? last.created : data.created);
    setText(card.querySelector("[data-mc-last-updated]"), last.updated != null ? last.updated : data.updated);
    var held = data.issues_open ? data.held : 0;
    setText(card.querySelector("[data-mc-last-held]"), held);
    var wrap = card.querySelector("[data-mc-last-held-wrap]");
    if (wrap) wrap.classList.toggle("rmc-badge--danger", held > 0);
    var note = card.querySelector("[data-mc-last-held-note]");
    var boardEl = board();
    if (note && boardEl) {
      note.textContent = held > 0
        ? boardEl.getAttribute("data-msg-held") || note.textContent
        : boardEl.getAttribute("data-msg-held-zero") || note.textContent;
    }
  }

  function paintRepairPanel(data) {
    var panel = document.getElementById("mc-repair-panel");
    if (!panel) return;
    var stuck = Boolean(data && data.import_stuck);
    var keep = Boolean(
      data &&
        (!data.importing || stuck) &&
        (data.repair || data.issues_open || (data.remediator && data.remediator.show_repair))
    );
    panel.hidden = !keep;
  }

  function csrfToken() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function postRepair(repairUrl) {
    if (!repairUrl || !window.fetch) return Promise.reject();
    var body = new URLSearchParams();
    body.set("csrfmiddlewaretoken", csrfToken());
    return fetch(repairUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: body.toString(),
    });
  }

  function postClearQueue(resolveUrl) {
    if (!resolveUrl || !window.fetch) return Promise.reject();
    return fetch(resolveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify({ action: "clear_queue", auto_retry: true }),
    });
  }

  function wireRecoveryActions(root) {
    if (!root) return;
    var repairUrl = root.getAttribute("data-repair-url");
    var resolveUrl = root.getAttribute("data-resolve-url");
    document.querySelectorAll("[data-mc-clear-queue]").forEach(function (btn) {
      if (btn.getAttribute("data-mc-clear-wired")) return;
      btn.setAttribute("data-mc-clear-wired", "1");
      btn.addEventListener("click", function () {
        if (!resolveUrl) return;
        if (!window.confirm("Clear the entire held queue? Safe rows dismiss automatically; the rest will be skipped.")) return;
        btn.disabled = true;
        postClearQueue(resolveUrl)
          .then(function (r) {
            if (!r.ok) throw new Error("clear failed");
            window.location.reload();
          })
          .catch(function () {
            btn.disabled = false;
            window.alert("Could not clear the queue. Try again from Review held rows.");
          });
      });
    });
    if (root.getAttribute("data-mc-repair-wired")) return;
    root.setAttribute("data-mc-repair-wired", "1");
  }

  function paint(root, data) {
    if (!root || !data) return;
    setText(root.querySelector("[data-mc-live-state]"), data.workflow_state);
    var pct = monotonicPercent(data);
    setText(root.querySelector("[data-mc-live-pct]"), pct.toFixed(2) + "%");
    setText(root.querySelector("[data-mc-live-created]"), data.created || 0);
    setText(root.querySelector("[data-mc-live-updated]"), data.updated || 0);
    setText(root.querySelector("[data-mc-live-held]"), data.held || 0);
    var heldWrap = root.querySelector("[data-mc-live-held-wrap]");
    if (heldWrap) heldWrap.classList.toggle("rmc-badge--danger", Number(data.held || 0) > 0);
    var fill = root.querySelector("[data-mc-live-fill]");
    if (fill) fill.style.width = pct.toFixed(2) + "%";
    paintPipeline(root, data.pipeline);
    paintRemediator(root, data.remediator);
    paintCanvas(data);
    paintLastImport(data);
    paintRepairPanel(data);
    var note = root.querySelector("[data-mc-live-note]");
    if (note && data.importing) {
      var running = data.import_phase === "running";
      note.textContent = data.import_stuck
        ? root.getAttribute(running ? "data-msg-wedged" : "data-msg-slow")
        : (running ? root.getAttribute("data-msg-running") : root.getAttribute("data-msg-queued"));
    } else if (note && data.succeeded) {
      // Settled and clean: say so explicitly. Previously the board just stopped
      // animating, which is exactly what a wedged import also looks like.
      note.textContent = root.getAttribute("data-msg-success") || note.textContent;
      root.setAttribute("data-mc-succeeded", "1");
    }
  }

  function start() {
    var root = board();
    if (!root || !window.fetch) return;
    var url = root.getAttribute("data-progress-url");
    if (!url) return;
    var streamUrl = root.getAttribute("data-progress-stream-url");
    var wasImporting = root.getAttribute("data-importing") === "1";
    var tries = 0;
    var seed = seedPayload();
    if (seed) {
      if (seed.importing) _maxPercentSeen = Number(seed.percent || 0) || 0;
      paint(root, seed);
    }
    wireRecoveryActions(root);

    function delay() {
      return wasImporting ? POLL_MS_ACTIVE : POLL_MS_SETTLED;
    }

    function applyProgressData(data) {
      if (!data) return;
      paint(root, data);
      if (data.importing) {
        wasImporting = true;
        if (data.import_stuck) {
          window.setTimeout(function () {
            window.location.reload();
          }, 1200);
          return true;
        }
        return false;
      }
      if (wasImporting) {
        window.location.reload();
        return true;
      }
      if (data.issues_open || (data.held && Number(data.held) > 0)) {
        return false;
      }
      if (data.succeeded) return true;
      return false;
    }

    function tick() {
      fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          if (!data) {
            window.setTimeout(tick, delay());
            return;
          }
          if (applyProgressData(data)) return;
          tries += 1;
          if (tries > MAX_ACTIVE_TRIES) {
            window.setTimeout(function () {
              window.location.reload();
            }, 800);
            return;
          }
          window.setTimeout(tick, data.importing ? POLL_MS_ACTIVE : POLL_MS_SETTLED);
        })
        .catch(function () {
          window.setTimeout(tick, delay());
        });
    }

    function startPolling() {
      window.setTimeout(tick, wasImporting ? 1200 : POLL_MS_SETTLED);
    }

    if (wasImporting && streamUrl && window.EventSource) {
      var es = new EventSource(streamUrl, { withCredentials: true });
      var pollFallbackTimer = window.setTimeout(startPolling, POLL_MS_ACTIVE * 2);
      es.onmessage = function () {
        window.clearTimeout(pollFallbackTimer);
        pollFallbackTimer = window.setTimeout(startPolling, POLL_MS_ACTIVE);
      };
      es.onerror = function () {
        try { es.close(); } catch (_err) {}
        window.clearTimeout(pollFallbackTimer);
        startPolling();
      };
      window.setTimeout(tick, 800);
      return;
    }

    startPolling();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
