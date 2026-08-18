/**
 * Page-local workflow telemetry canvas.
 * Same-origin WebSocket + SSE chip events. Never joins a client-supplied tenant room.
 */
(function () {
  "use strict";

  var DONE_STATUSES = {
    succeeded: true,
    COMPLETED: true,
    failed: true,
    FAILED: true,
  };

  function canvases() {
    return Array.prototype.slice.call(
      document.querySelectorAll("[data-rmc-wfp-canvas]")
    );
  }

  function matchesCanvas(el, payload) {
    if (!payload) return false;
    var key = (el.getAttribute("data-rmc-workflow-key") || "").trim();
    var task = (el.getAttribute("data-rmc-workflow-task") || "").trim();
    var frameKey = String(payload.workflow_key || "");
    var frameTask = String(payload.task_type || "");
    if (key && frameKey && key !== frameKey) return false;
    if (task && frameTask && task !== frameTask) return false;
    if (key && !frameKey && task && !frameTask) return false;
    if (key && !frameKey && task && frameTask && task !== frameTask) return false;
    if (!key && !task) return true;
    if (key && !frameKey && !task) return true;
    if (!key && task && frameTask === task) return true;
    if (key && frameKey === key) return true;
    return false;
  }

  function formatPercent(value) {
    var raw = String(value == null ? "0" : value);
    if (raw.indexOf("%") >= 0) return raw;
    var num = Number(raw);
    if (!isFinite(num)) return raw + "%";
    return num.toFixed(2) + "%";
  }

  function formatCount(value) {
    var n = Number(value);
    if (!isFinite(n)) return String(value || 0);
    try {
      return n.toLocaleString();
    } catch (_err) {
      return String(n);
    }
  }

  function appendLog(terminal, line) {
    if (!terminal || !line) return;
    var empty = terminal.querySelector("[data-rmc-wfp-empty]");
    if (empty) empty.remove();
    var row = document.createElement("div");
    row.className = "rmc-wfp-canvas__log-line";
    row.textContent = line;
    terminal.appendChild(row);
    terminal.scrollTop = terminal.scrollHeight;
  }

  function applyFrame(el, frame) {
    var payload = (frame && frame.payload) || frame || {};
    if (!matchesCanvas(el, payload)) return false;
    var fill = el.querySelector("[data-rmc-wfp-fill]");
    var pct = el.querySelector("[data-rmc-wfp-pct]");
    var processed = el.querySelector("[data-rmc-wfp-processed]");
    var expected = el.querySelector("[data-rmc-wfp-expected]");
    var terminal = el.querySelector("[data-rmc-wfp-log]");
    var percent = payload.percent_complete;
    if (fill) fill.style.width = formatPercent(percent);
    if (pct) pct.textContent = formatPercent(percent);
    if (processed) processed.textContent = formatCount(payload.processed_count);
    if (expected) expected.textContent = formatCount(payload.expected_count);
    var logLine = payload.latest_trace_log || "";
    if (logLine) {
      var stamp = frame.emitted_at ? new Date(frame.emitted_at).toLocaleTimeString() : "";
      appendLog(terminal, stamp ? "[" + stamp + "] " + logLine : logLine);
    }
    var status = String(payload.current_status || "");
    el.setAttribute("data-rmc-wfp-state", status || "running");
    return DONE_STATUSES[status] === true;
  }

  function applyToMatching(frame) {
    var payload = (frame && frame.payload) || frame || {};
    var done = false;
    canvases().forEach(function (el) {
      if (applyFrame(el, frame || { payload: payload })) done = true;
    });
    return done;
  }

  function websocketUrl() {
    var proto = window.location.protocol === "https:" ? "wss://" : "ws://";
    return proto + window.location.host + "/ws/workflow-progress/";
  }

  function connectSocket() {
    if (!canvases().length) return;
    var socket;
    try {
      socket = new WebSocket(websocketUrl());
    } catch (_err) {
      return;
    }
    socket.onmessage = function (event) {
      var frame;
      try {
        frame = JSON.parse(event.data || "{}");
      } catch (_parseErr) {
        return;
      }
      if (frame.event_type && frame.event_type !== "WORKFLOW_PROGRESS_UPDATE") return;
      var done = applyToMatching(frame);
      if (done) {
        try {
          socket.close();
        } catch (_closeErr) {}
      }
    };
  }

  function onChipEvent(event) {
    var detail = event && event.detail;
    if (!detail) return;
    var runs = detail.runs || [];
    runs.forEach(function (run) {
      applyToMatching({
        event_type: "WORKFLOW_PROGRESS_UPDATE",
        emitted_at: run.updated_at || "",
        payload: {
          workflow_key: run.workflow_key || "",
          task_type: run.task_type || "",
          percent_complete: run.percent_complete || run.progress_percent || 0,
          processed_count: run.records_processed || 0,
          expected_count: run.records_expected || 0,
          current_status: run.status || "",
          latest_trace_log: (run.log_history && run.log_history.length)
            ? run.log_history[run.log_history.length - 1]
            : (run.current_step_name || ""),
        },
      });
    });
  }

  document.addEventListener("rmc:workflow-progress", onChipEvent);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", connectSocket);
  } else {
    connectSocket();
  }

  function holdSubmit(event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!form.hasAttribute("data-rmc-wfp-hold")) return;
    if (!canvases().length) return;
    if (typeof window.fetch !== "function") return;
    var submitter = event.submitter;
    if (submitter && submitter.getAttribute("name") === "create_backup_now") return;
    event.preventDefault();
    var data = new FormData(form);
    if (submitter && submitter.name) {
      data.append(submitter.name, submitter.value || "1");
    }
    var buttons = form.querySelectorAll("button[type='submit'], input[type='submit']");
    buttons.forEach(function (btn) {
      btn.disabled = true;
    });
    applyToMatching({
      event_type: "WORKFLOW_PROGRESS_UPDATE",
      emitted_at: new Date().toISOString(),
      payload: {
        workflow_key: (canvases()[0].getAttribute("data-rmc-workflow-key") || "").trim(),
        task_type: (canvases()[0].getAttribute("data-rmc-workflow-task") || "").trim(),
        percent_complete: "0.00",
        processed_count: 0,
        expected_count: 0,
        current_status: "running",
        latest_trace_log: "",
      },
    });
    window
      .fetch(form.action || window.location.href, {
        method: (form.method || "POST").toUpperCase(),
        body: data,
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        redirect: "manual",
      })
      .then(function (resp) {
        var stay = form.hasAttribute("data-rmc-wfp-stay");
        if (stay) {
          var ctype = (resp.headers.get("Content-Type") || "").toLowerCase();
          if (ctype.indexOf("application/json") >= 0) {
            return resp.json().then(function (body) {
              document.dispatchEvent(
                new CustomEvent("rmc:sync-center-status", { detail: body || {} })
              );
              var phase = body && body.phase;
              if (phase !== "running") {
                buttons.forEach(function (btn) {
                  btn.disabled = false;
                });
              }
            });
          }
          document.dispatchEvent(new CustomEvent("rmc:sync-center-poll"));
          return;
        }
        var loc = resp.headers.get("Location");
        if (loc) {
          window.location.assign(loc);
          return;
        }
        window.location.reload();
      })
      .catch(function () {
        buttons.forEach(function (btn) {
          btn.disabled = false;
        });
        form.submit();
      });
  }

  document.addEventListener("submit", holdSubmit, true);
})();
