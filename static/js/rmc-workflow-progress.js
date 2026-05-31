/**
 * RunMyCampus Workflow Progress Bus — frontend chip controller (v4.00.96).
 *
 * Architecture:
 * - Mounts a floating chip in the body. Connects to /platform/workflow-progress/stream/
 *   via EventSource. On every snapshot event, re-renders the expanded card with
 *   the step train + ETA + AI-suggested fix card when applicable.
 * - Gracefully degrades on no-EventSource environments by polling /badge/.
 * - Reduced-motion + small-screen friendly; full keyboard support (g w shortcut).
 */
(function () {
  "use strict";

  if (window.__rmcWorkflowProgressMounted) return;
  window.__rmcWorkflowProgressMounted = true;

  var ENDPOINT_STREAM = "/platform-runtime/workflow-progress/stream/";
  var ENDPOINT_ACTIVE = "/platform-runtime/workflow-progress/active/";
  var ENDPOINT_BADGE = "/platform-runtime/workflow-progress/badge/";
  var ENDPOINT_CANCEL = "/platform-runtime/workflow-progress/cancel/";
  var ENDPOINT_APPLY_FIX = "/platform-runtime/workflow-progress/apply-fix/";

  // Polling fallback cadence (ms) when EventSource unavailable.
  var POLL_INTERVAL_MS = 5000;

  var state = {
    runs: [],
    open: false,
    eventSource: null,
    pollTimer: null,
    everyConnected: false,
  };

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getCsrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function buildChip() {
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "rmc-wfp-chip";
    chip.id = "rmc-wfp-chip";
    chip.setAttribute("aria-label", "Workflow progress");
    chip.setAttribute("aria-haspopup", "dialog");
    chip.setAttribute("aria-expanded", "false");
    chip.setAttribute("aria-keyshortcuts", "g w");
    chip.dataset.rmcWfpState = "idle";
    chip.innerHTML =
      '<i class="bi bi-hourglass-split rmc-wfp-chip__icon" aria-hidden="true"></i>' +
      '<span class="rmc-wfp-chip__count" hidden>0</span>';
    return chip;
  }

  function buildCard() {
    var card = document.createElement("div");
    card.className = "rmc-wfp-card";
    card.id = "rmc-wfp-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-labelledby", "rmc-wfp-card-title");
    card.dataset.rmcWfpOpen = "false";
    card.innerHTML =
      '<div class="rmc-wfp-card__header">' +
      '<span class="rmc-wfp-card__title" id="rmc-wfp-card-title">' +
      '<i class="bi bi-hourglass-split" aria-hidden="true"></i> Workflow Progress' +
      "</span>" +
      '<button type="button" class="rmc-wfp-card__close" aria-label="Close">' +
      '<i class="bi bi-x-lg" aria-hidden="true"></i>' +
      "</button>" +
      "</div>" +
      '<div class="rmc-wfp-card__body" id="rmc-wfp-card-body"></div>';
    return card;
  }

  function renderCard() {
    var body = document.getElementById("rmc-wfp-card-body");
    if (!body) return;
    if (!state.runs.length) {
      body.innerHTML =
        '<div class="rmc-wfp-card__empty">' +
        '<i class="bi bi-check-circle" aria-hidden="true" style="font-size:1.5rem;display:block;margin-bottom:0.4rem;"></i>' +
        "No active workflows. The platform is idle." +
        "</div>";
      return;
    }
    var html = "";
    for (var i = 0; i < state.runs.length; i++) {
      html += renderRun(state.runs[i]);
    }
    body.innerHTML = html;
    wireRunActions(body);
  }

  function renderRun(run) {
    var status = run.status || "running";
    var pillClass = "rmc-wfp-run__pill--" + status;
    var label = escapeHtml(run.workflow_label || run.workflow_key || "Workflow");
    var current = escapeHtml(run.current_step_name || "starting…");
    var ordinal = run.current_step_ordinal || 0;
    var total = run.total_steps || 0;
    var ageSeconds = ageInSeconds(run.started_at);
    var ageText = ageSeconds < 60
      ? ageSeconds + "s"
      : Math.round(ageSeconds / 60) + "m" + (ageSeconds % 60 === 0 ? "" : " " + (ageSeconds % 60) + "s");
    var etaSeconds = Math.max(0, (run.expected_duration_seconds || 30) - ageSeconds);
    var etaText = etaSeconds === 0 ? "overdue" : "~" + etaSeconds + "s left";

    var train = renderTrain(ordinal, total, status);
    var fix = run.suggested_remediation && Object.keys(run.suggested_remediation).length
      ? renderFix(run)
      : "";

    return (
      '<div class="rmc-wfp-run" data-rmc-wfp-state="' + escapeHtml(status) + '" data-run-id="' + escapeHtml(run.id) + '">' +
      '<div class="rmc-wfp-run__head">' +
      "<div>" +
      '<div class="rmc-wfp-run__title">' + label + "</div>" +
      '<div class="rmc-wfp-run__meta">' + (run.tenant_schema ? escapeHtml(run.tenant_schema) + " · " : "") + ageText + ' ago</div>' +
      "</div>" +
      '<span class="rmc-wfp-run__pill ' + pillClass + '">' + escapeHtml(status) + "</span>" +
      "</div>" +
      '<div class="rmc-wfp-train">' + train + "</div>" +
      '<div class="rmc-wfp-run__step-row">' +
      "<span>Step " + ordinal + (total ? " / " + total : "") + ": <strong>" + current + "</strong></span>" +
      "<span>" + etaText + "</span>" +
      "</div>" +
      fix +
      "</div>"
    );
  }

  function renderTrain(currentOrdinal, total, status) {
    if (!total || total < 1) {
      // No declared steps — show a single living bead.
      return '<span class="rmc-wfp-train__bead" data-status="' + escapeHtml(status === "stuck" ? "failed" : "running") + '"></span>';
    }
    var html = "";
    for (var i = 1; i <= total; i++) {
      var beadStatus;
      if (i < currentOrdinal) beadStatus = "done";
      else if (i === currentOrdinal) beadStatus = status === "stuck" ? "failed" : "running";
      else beadStatus = "pending";
      html += '<span class="rmc-wfp-train__bead" data-status="' + beadStatus + '"></span>';
      if (i < total) html += '<span class="rmc-wfp-train__rule"></span>';
    }
    return html;
  }

  function renderFix(run) {
    var rem = run.suggested_remediation || {};
    if (!rem.human_action) return "";
    var canApply = !!rem.auto_fix_available;
    return (
      '<div class="rmc-wfp-fix" data-run-id="' + escapeHtml(run.id) + '">' +
      '<div class="rmc-wfp-fix__title">AI suggested fix</div>' +
      '<div class="rmc-wfp-fix__body">' + escapeHtml(rem.human_action) + "</div>" +
      '<div class="rmc-wfp-fix__actions">' +
      (canApply
        ? '<button type="button" class="rmc-wfp-fix__btn" data-rmc-wfp-action="apply-fix">Apply</button>'
        : "") +
      '<button type="button" class="rmc-wfp-fix__btn rmc-wfp-fix__btn--ghost" data-rmc-wfp-action="cancel">Cancel run</button>' +
      "</div>" +
      "</div>"
    );
  }

  function ageInSeconds(startIso) {
    if (!startIso) return 0;
    try {
      var started = new Date(startIso).getTime();
      var now = Date.now();
      return Math.max(0, Math.floor((now - started) / 1000));
    } catch (_) {
      return 0;
    }
  }

  function wireRunActions(root) {
    var btns = root.querySelectorAll("[data-rmc-wfp-action]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", onRunAction);
    }
  }

  function onRunAction(evt) {
    var action = evt.currentTarget.getAttribute("data-rmc-wfp-action");
    var card = evt.currentTarget.closest("[data-run-id]");
    if (!card) return;
    var runId = card.getAttribute("data-run-id");
    if (!runId) return;
    var url = "";
    if (action === "apply-fix") url = ENDPOINT_APPLY_FIX + runId + "/";
    else if (action === "cancel") url = ENDPOINT_CANCEL + runId + "/";
    else return;
    fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        "Accept": "application/json",
      },
      credentials: "same-origin",
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        // Soft-refresh; the next SSE tick will pick up the state change.
        if (j && j.ok) {
          card.style.opacity = "0.5";
        }
      })
      .catch(function () { /* network failures are surfaced on next tick */ });
  }

  function updateChip() {
    var chip = document.getElementById("rmc-wfp-chip");
    if (!chip) return;
    var stuck = 0;
    var running = 0;
    for (var i = 0; i < state.runs.length; i++) {
      if (state.runs[i].status === "stuck") stuck++;
      else if (state.runs[i].status === "running") running++;
    }
    var chipState;
    if (stuck > 0) chipState = "stuck";
    else if (running > 0) chipState = "running";
    else chipState = "idle";
    chip.dataset.rmcWfpState = chipState;
    var countEl = chip.querySelector(".rmc-wfp-chip__count");
    if (countEl) {
      var total = stuck + running;
      if (total > 0) {
        countEl.textContent = String(total);
        countEl.hidden = false;
      } else {
        countEl.hidden = true;
      }
    }
  }

  function applySnapshot(payload) {
    if (!payload || !Array.isArray(payload.runs)) return;
    state.runs = payload.runs;
    updateChip();
    if (state.open) renderCard();
  }

  function agentDebugLog(hypothesisId, location, message, data) {
    // #region agent log
    fetch("http://127.0.0.1:7426/ingest/383483ef-728e-4a6f-8288-6731caa89dc7", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "0f968b" },
      body: JSON.stringify({
        sessionId: "0f968b",
        hypothesisId: hypothesisId,
        location: location,
        message: message,
        data: data || {},
        timestamp: Date.now(),
      }),
    }).catch(function () {});
    // #endregion
  }

  function shouldConnectStream() {
    if (document.querySelector("[data-rmc-auth-landing]")) return false;
    return true;
  }

  function connectStream() {
    if (!shouldConnectStream()) {
      agentDebugLog("H2", "rmc-workflow-progress.js:connectStream", "skip_auth_landing", {});
      return;
    }
    if (typeof EventSource === "undefined") {
      startPolling();
      return;
    }
    try {
      agentDebugLog("H4", "rmc-workflow-progress.js:connectStream", "event_source_open", {});
      var es = new EventSource(ENDPOINT_STREAM, { withCredentials: true });
      state.eventSource = es;
      state.everyConnected = true;
      es.addEventListener("snapshot", function (ev) {
        try {
          applySnapshot(JSON.parse(ev.data));
        } catch (_) { /* malformed frame — ignore */ }
      });
      es.addEventListener("bye", function () {
        // Server-side graceful close; reconnect after a small jitter.
        es.close();
        state.eventSource = null;
        setTimeout(connectStream, 800 + Math.floor(Math.random() * 800));
      });
      es.onerror = function () {
        es.close();
        state.eventSource = null;
        agentDebugLog("H3", "rmc-workflow-progress.js:connectStream", "event_source_error", {});
        fetch(ENDPOINT_ACTIVE, { credentials: "same-origin" })
          .then(function (r) {
            if (r.status === 401 || r.status === 403) {
              agentDebugLog("H1", "rmc-workflow-progress.js:connectStream", "auth_required_no_reconnect", { status: r.status });
              return;
            }
            setTimeout(connectStream, 4000);
          })
          .catch(function () {
            setTimeout(connectStream, 4000);
          });
      };
    } catch (_) {
      startPolling();
    }
  }

  function startPolling() {
    if (state.pollTimer) return;
    state.pollTimer = window.setInterval(function () {
      fetch(ENDPOINT_ACTIVE, { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(applySnapshot)
        .catch(function () { /* ignore — next tick will retry */ });
    }, POLL_INTERVAL_MS);
    // Kick once immediately.
    fetch(ENDPOINT_ACTIVE, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(applySnapshot)
      .catch(function () { /* ignore */ });
  }

  function toggleCard() {
    state.open = !state.open;
    var chip = document.getElementById("rmc-wfp-chip");
    var card = document.getElementById("rmc-wfp-card");
    if (!chip || !card) return;
    chip.setAttribute("aria-expanded", state.open ? "true" : "false");
    card.dataset.rmcWfpOpen = state.open ? "true" : "false";
    if (state.open) renderCard();
  }

  function onKeydown(evt) {
    // g w shortcut.
    if (evt.target && (evt.target.tagName === "INPUT" || evt.target.tagName === "TEXTAREA" || evt.target.isContentEditable)) {
      return;
    }
    if (evt.key === "g" && !evt.repeat) {
      window.__rmcWfpGPending = Date.now();
      window.setTimeout(function () { window.__rmcWfpGPending = 0; }, 1000);
      return;
    }
    if (evt.key === "w" && window.__rmcWfpGPending && (Date.now() - window.__rmcWfpGPending) < 1000) {
      window.__rmcWfpGPending = 0;
      toggleCard();
    }
    if (evt.key === "Escape" && state.open) {
      toggleCard();
    }
  }

  function mount() {
    if (document.getElementById("rmc-wfp-chip")) return;
    var chip = buildChip();
    var card = buildCard();
    document.body.appendChild(card);

    // Park the chip into the assist-dock host if it exists; otherwise float bottom-right.
    var dock = document.querySelector('[data-rmc-assist-dock-host],[data-rmc-assist-dock="mounted"]');
    if (dock) {
      dock.appendChild(chip);
    } else {
      chip.style.position = "fixed";
      chip.style.right = "1rem";
      chip.style.bottom = "calc(env(safe-area-inset-bottom, 0px) + 5.5rem)";
      chip.style.zIndex = "10465";
      document.body.appendChild(chip);
    }

    chip.addEventListener("click", toggleCard);
    var closeBtn = card.querySelector(".rmc-wfp-card__close");
    if (closeBtn) closeBtn.addEventListener("click", toggleCard);
    document.addEventListener("keydown", onKeydown);

    connectStream();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
