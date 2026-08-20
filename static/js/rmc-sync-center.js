/**
 * Sync Center live status + bulk conflict resolve.
 * Polls school-scoped JSON; never invents counts. Paints the workflow canvas
 * from the same payload when Channels is quiet.
 */
(function () {
  "use strict";

  var POLL_FLOOR_MS = 1500;
  var BADGE_CLASS = {
    ok: "badge rounded-pill bg-success-subtle text-success-emphasis",
    failed: "badge rounded-pill bg-danger-subtle text-danger-emphasis",
    queued: "badge rounded-pill bg-warning-subtle text-warning-emphasis",
    running: "badge rounded-pill bg-warning-subtle text-warning-emphasis",
    idle: "badge rounded-pill bg-body-secondary text-body-secondary",
  };

  function root() {
    return document.querySelector("[data-rmc-sync-center]");
  }

  function setText(selector, value) {
    var el = document.querySelector(selector);
    if (el) el.textContent = value == null ? "" : String(value);
  }

  function applyCanvas(payload) {
    if (!payload || typeof window === "undefined") return;
    var canvases = document.querySelectorAll("[data-rmc-wfp-canvas]");
    if (!canvases.length) return;
    var frame = {
      event_type: "WORKFLOW_PROGRESS_UPDATE",
      emitted_at: new Date().toISOString(),
      payload: {
        workflow_key: payload.workflow_key || "siteconfig-edge-sync",
        task_type: payload.task_type || "EDGE_SYNC",
        percent_complete: payload.percent_complete || "0.00",
        processed_count: payload.processed || 0,
        expected_count: payload.expected || 0,
        current_status: payload.current_status || payload.phase || "",
        latest_trace_log: payload.latest_trace_log || payload.headline || "",
      },
    };
    canvases.forEach(function (el) {
      var fill = el.querySelector("[data-rmc-wfp-fill]");
      var pct = el.querySelector("[data-rmc-wfp-pct]");
      var processed = el.querySelector("[data-rmc-wfp-processed]");
      var expected = el.querySelector("[data-rmc-wfp-expected]");
      var terminal = el.querySelector("[data-rmc-wfp-log]");
      var percent = String(frame.payload.percent_complete);
      if (percent.indexOf("%") < 0) percent = percent + "%";
      if (fill) fill.style.width = percent;
      if (pct) pct.textContent = percent;
      if (processed) processed.textContent = String(frame.payload.processed_count);
      if (expected) expected.textContent = String(frame.payload.expected_count);
      if (terminal && frame.payload.latest_trace_log) {
        var empty = terminal.querySelector("[data-rmc-wfp-empty]");
        if (empty) empty.remove();
        var last = terminal.querySelector("[data-rmc-sync-last-log]");
        if (!last) {
          last = document.createElement("div");
          last.className = "rmc-wfp-canvas__log-line";
          last.setAttribute("data-rmc-sync-last-log", "1");
          terminal.appendChild(last);
        }
        last.textContent = frame.payload.latest_trace_log;
      }
    });
  }

  function label(kind) {
    var host = root();
    var key = "data-rmc-label-" + kind;
    var fallback = { running: "Running", ok: "OK", failed: "Failed" };
    if (!host) return fallback[kind] || kind;
    return host.getAttribute(key) || fallback[kind] || kind;
  }

  function renderRecent(runs) {
    var list = document.querySelector("[data-rmc-sync-recent]");
    if (!list) return;
    list.innerHTML = "";
    if (!runs || !runs.length) {
      list.classList.add("d-none");
      return;
    }
    list.classList.remove("d-none");
    runs.forEach(function (run) {
      var li = document.createElement("li");
      var state = run.in_progress ? "running" : run.ok ? "ok" : "failed";
      li.textContent =
        label(state) +
        " — " +
        (run.created_at || "") +
        " (pushed " +
        (run.pushed || 0) +
        ", pulled " +
        (run.pulled || 0) +
        ")";
      // The reason ships in the payload already. Rendering only the state left a
      // school staring at "Failed" with nothing to act on. textContent, not
      // innerHTML: this string is server data and must never be parsed as markup.
      var reason = run.error || run.message || "";
      if (reason) {
        var note = document.createElement("div");
        note.className = run.error ? "text-danger-emphasis" : "text-body-secondary";
        note.textContent = reason;
        li.appendChild(note);
      }
      list.appendChild(li);
    });
  }

  function setSyncButtonsDisabled(disabled) {
    var form = document.querySelector("[data-rmc-wfp-stay]");
    if (!form) return;
    form.querySelectorAll("button[type='submit'], input[type='submit']").forEach(function (btn) {
      btn.disabled = Boolean(disabled);
    });
  }

  function applyStatus(payload) {
    if (!payload || !payload.ok) return;
    var badge = document.querySelector("[data-rmc-sync-badge]");
    if (badge) {
      var phase = payload.phase || "idle";
      badge.className = BADGE_CLASS[phase] || BADGE_CLASS.idle;
      badge.setAttribute("data-phase", phase);
      badge.textContent = payload.badge || phase;
    }
    setText("[data-rmc-sync-headline]", payload.headline || "");
    setText("[data-rmc-sync-pushed]", payload.pushed || 0);
    setText("[data-rmc-sync-pulled]", payload.pulled || 0);
    setText("[data-rmc-sync-conflicts]", payload.conflicts || 0);
    setText("[data-rmc-sync-stat-pending]", payload.pending_conflicts || 0);
    var queueBtn = document.querySelector("[data-rmc-sync-queue-btn]");
    if (queueBtn) queueBtn.disabled = Boolean(payload.pending_resync);
    renderRecent(payload.recent_runs);
    applyCanvas(payload);
    setSyncButtonsDisabled(payload.phase === "running");
  }

  function poll() {
    var host = root();
    if (!host) return;
    var url = host.getAttribute("data-status-url");
    if (!url || typeof window.fetch !== "function") return;
    window
      .fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (resp) {
        return resp.ok ? resp.json() : null;
      })
      .then(function (payload) {
        if (payload) applyStatus(payload);
      })
      .catch(function () {
        /* next tick retries */
      });
  }

  function wireProbe() {
    var host = root();
    if (!host) return;
    var btn = document.querySelector("[data-rmc-sync-probe-btn]");
    var out = document.querySelector("[data-rmc-sync-probe-result]");
    var url = host.getAttribute("data-probe-url");
    if (!btn || !url || typeof window.fetch !== "function") return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      if (out) {
        out.textContent = "…";
        out.classList.remove("d-none", "text-danger-emphasis", "text-success-emphasis");
        out.classList.add("text-body-secondary");
      }
      var csrfEl = document.querySelector("[name=csrfmiddlewaretoken]");
      var csrf = csrfEl ? csrfEl.value : "";
      window
        .fetch(url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrf,
            Accept: "application/json",
          },
        })
        .then(function (resp) {
          return resp.json().then(function (body) {
            return { body: body };
          });
        })
        .then(function (pack) {
          var body = pack.body || {};
          var lines = [];
          if (body.probes && body.probes.pull) {
            lines.push(
              "Pull: HTTP " +
                String(body.probes.pull.status || "?") +
                " — " +
                (body.probes.pull.detail || "")
            );
          }
          if (body.probes && body.probes.push) {
            lines.push(
              "Push: HTTP " +
                String(body.probes.push.status || "?") +
                " — " +
                (body.probes.push.detail || "")
            );
          }
          (body.problems || []).forEach(function (p) {
            if (lines.indexOf(p) < 0) lines.push(p);
          });
          if (out) {
            out.textContent = lines.length ? lines.join(" ") : body.error || "Done.";
            out.classList.toggle("text-success-emphasis", !!body.ok);
            out.classList.toggle("text-danger-emphasis", !body.ok);
            out.classList.remove("text-body-secondary");
          }
        })
        .catch(function () {
          if (out) {
            out.textContent = "Could not run cloud probe.";
            out.classList.add("text-danger-emphasis");
          }
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  }

  function wireBulk() {
    var table = document.getElementById("sync-conflicts-table");
    var host = root();
    if (!table || !host) return;
    var url = host.getAttribute("data-bulk-url");
    table.addEventListener("rmc:bulk-action", function (ev) {
      var detail = ev.detail || {};
      var ids = detail.ids || [];
      var action = detail.action || "";
      if (!ids.length || !action) return;
      var poster =
        (window.rmcBulkActions && window.rmcBulkActions.postWithCsrf) || null;
      if (!poster) return;
      poster(url, { ids: ids, resolution: action }).then(function (resp) {
        if (resp && resp.ok) {
          window.location.reload();
          return;
        }
        return resp.json().then(function (body) {
          var msg = document.querySelector("[data-rmc-sync-bulk-msg]");
          if (msg) {
            msg.textContent =
              (body && body.message) ||
              (host && host.getAttribute("data-rmc-bulk-error")) ||
              "Could not resolve conflicts.";
            msg.classList.remove("d-none");
          }
        });
      });
    });
  }

  function start() {
    wireBulk();
    wireProbe();
    var host = root();
    if (!host) return;
    poll();
    var ms = Number(host.getAttribute("data-poll-ms") || 3000);
    if (!isFinite(ms) || ms < POLL_FLOOR_MS) ms = 3000;
    window.setInterval(poll, ms);
    document.addEventListener("rmc:sync-center-status", function (ev) {
      applyStatus(ev.detail || {});
    });
    document.addEventListener("rmc:sync-center-poll", poll);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
