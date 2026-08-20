/**
 * Migration Cloud kickoff live board.
 * Polls the tenant-scoped bundle progress JSON and paints pipeline / counts /
 * remediator on the Review & Import page. Reloads once when an in-flight apply
 * settles. Hides held / repair chrome the moment issue_count is 0.
 */
(function () {
  "use strict";

  var POLL_MS_ACTIVE = 1800;
  var POLL_MS_SETTLED = 5000;
  var MAX_ACTIVE_TRIES = 160;

  function board() {
    return document.getElementById("mc-live-board");
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

  function paintCanvas(data) {
    var el = document.querySelector("[data-rmc-wfp-canvas]");
    if (!el || !data) return;
    var fill = el.querySelector("[data-rmc-wfp-fill]");
    var pct = el.querySelector("[data-rmc-wfp-pct]");
    var processed = el.querySelector("[data-rmc-wfp-processed]");
    var expected = el.querySelector("[data-rmc-wfp-expected]");
    var percent = Number(data.percent || 0);
    if (!isFinite(percent)) percent = 0;
    if (fill) fill.style.width = percent.toFixed(2) + "%";
    if (pct) pct.textContent = percent.toFixed(2) + "%";
    if (processed) processed.textContent = String(data.processed || 0);
    if (expected) expected.textContent = String(data.expected || 0);
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
    var keep = Boolean(data && (data.repair || data.issues_open || (data.remediator && !data.importing)));
    panel.hidden = !keep;
  }

  function paint(root, data) {
    if (!root || !data) return;
    setText(root.querySelector("[data-mc-live-state]"), data.workflow_state);
    var pct = Number(data.percent || 0);
    if (!isFinite(pct)) pct = 0;
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
    var wasImporting = root.getAttribute("data-importing") === "1";
    var tries = 0;
    var seed = seedPayload();
    if (seed) paint(root, seed);

    function delay() {
      return wasImporting ? POLL_MS_ACTIVE : POLL_MS_SETTLED;
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
          paint(root, data);
          if (data.importing) {
            wasImporting = true;
            tries += 1;
            if (data.import_stuck && data.import_phase === "running") {
              window.setTimeout(function () {
                window.location.reload();
              }, 1200);
              return;
            }
            if (tries > MAX_ACTIVE_TRIES) {
              window.setTimeout(function () {
                window.location.reload();
              }, 800);
              return;
            }
            window.setTimeout(tick, POLL_MS_ACTIVE);
            return;
          }
          if (wasImporting) {
            window.location.reload();
            return;
          }
          // Terminal + clean: stop polling. Nothing further can change here, so
          // continuing to hit the endpoint every few seconds is pure noise.
          if (data.succeeded) return;
          window.setTimeout(tick, POLL_MS_SETTLED);
        })
        .catch(function () {
          window.setTimeout(tick, delay());
        });
    }

    window.setTimeout(tick, wasImporting ? 1200 : POLL_MS_SETTLED);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
