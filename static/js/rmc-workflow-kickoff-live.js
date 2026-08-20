/**
 * Shared kickoff live board for every workflow engine.
 * Polls /platform/workflow-progress/kickoff/ and paints pipeline + remediator.
 * Remediator is hidden the moment issues_open is 0.
 */
(function () {
  "use strict";

  var POLL_MS_ACTIVE = 1800;
  var POLL_MS_SETTLED = 8000;
  var MAX_ACTIVE_TRIES = 200;
  var started = false;

  function boards() {
    return document.querySelectorAll("[data-rmc-kickoff-live]");
  }

  function setText(el, value) {
    if (el) el.textContent = value == null ? "" : String(value);
  }

  function paintPipeline(root, stages) {
    var list = root.querySelector("[data-rmc-kickoff-pipeline]");
    if (!list) return;
    if (!stages || !stages.length) {
      list.hidden = true;
      list.innerHTML = "";
      return;
    }
    list.hidden = false;
    list.innerHTML = "";
    for (var i = 0; i < stages.length; i++) {
      var stage = stages[i] || {};
      var li = document.createElement("li");
      li.className =
        "rmc-wfp-pipeline__stage rmc-wfp-pipeline__stage--" +
        (stage.visual || "pending");
      li.setAttribute("data-rmc-stage", stage.key || stage.name || "");
      var bead = document.createElement("span");
      bead.className = "rmc-wfp-pipeline__bead";
      bead.setAttribute("aria-hidden", "true");
      var label = document.createElement("span");
      label.className = "rmc-wfp-pipeline__label";
      label.textContent = stage.label || stage.name || "";
      li.appendChild(bead);
      li.appendChild(label);
      list.appendChild(li);
    }
  }

  function paintMetrics(root, data) {
    var host = root.querySelector("[data-rmc-kickoff-metrics]");
    if (!host) return;
    var orch = Number(data.orchestration_open || 0);
    var auto = Number(data.automation_open || 0);
    var bus = Number(data.progress_bus_open || 0);
    var appr = Number(data.approvals_pending || 0);
    var show =
      data.engine === "all" || orch + auto + bus + appr > 0 || data.attention;
    host.hidden = !show;
    setText(root.querySelector("[data-rmc-kickoff-orch]"), orch);
    setText(root.querySelector("[data-rmc-kickoff-auto]"), auto);
    setText(root.querySelector("[data-rmc-kickoff-bus]"), bus);
    setText(root.querySelector("[data-rmc-kickoff-appr]"), appr);
  }

  function paintRemediator(root, remediator, issuesOpen) {
    var host = root.querySelector("[data-rmc-kickoff-remediator]");
    if (!host) return;
    if (!remediator || !issuesOpen) {
      host.hidden = true;
      setText(host.querySelector("[data-rmc-kickoff-rem-title]"), "");
      setText(host.querySelector("[data-rmc-kickoff-rem-error]"), "");
      var steps = host.querySelector("[data-rmc-kickoff-rem-steps]");
      if (steps) steps.innerHTML = "";
      return;
    }
    host.hidden = false;
    setText(
      host.querySelector("[data-rmc-kickoff-rem-title]"),
      remediator.title || ""
    );
    setText(
      host.querySelector("[data-rmc-kickoff-rem-error]"),
      remediator.error_message || remediator.error_type || ""
    );
    var ol = host.querySelector("[data-rmc-kickoff-rem-steps]");
    if (ol) {
      ol.innerHTML = "";
      var book = remediator.runbook_steps || [];
      for (var i = 0; i < book.length; i++) {
        var li = document.createElement("li");
        li.textContent = String(book[i] || "");
        ol.appendChild(li);
      }
    }
  }

  function paintCanvas(root, data) {
    var el = root.querySelector("[data-rmc-wfp-canvas]");
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

  function paint(root, data) {
    if (!root || !data) return;
    var issues = Number(data.issues_open || 0);
    var pct = Number(data.percent || 0);
    setText(
      root.querySelector("[data-rmc-kickoff-pct]"),
      (isFinite(pct) ? pct : 0).toFixed(0) + "%"
    );
    paintPipeline(root, data.pipeline || []);
    paintMetrics(root, data);
    paintRemediator(root, data.remediator, issues > 0);
    paintCanvas(root, data);
  }

  function poll(root, tries) {
    var url = root.getAttribute("data-rmc-kickoff-url");
    if (!url) return;
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (resp) {
        if (!resp.ok) throw new Error("kickoff " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        paint(root, data);
        var active = Boolean(data.in_flight) || Number(data.issues_open || 0) > 0;
        var next = active ? POLL_MS_ACTIVE : POLL_MS_SETTLED;
        if (active && tries + 1 >= MAX_ACTIVE_TRIES) next = POLL_MS_SETTLED;
        window.setTimeout(function () {
          poll(root, active ? tries + 1 : 0);
        }, next);
      })
      .catch(function () {
        window.setTimeout(function () {
          poll(root, tries);
        }, POLL_MS_SETTLED);
      });
  }

  function boot() {
    if (window.__rmcKickoffLiveBoot) return;
    var nodes = boards();
    if (!nodes.length) return;
    window.__rmcKickoffLiveBoot = true;
    started = true;
    for (var i = 0; i < nodes.length; i++) {
      poll(nodes[i], 0);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
