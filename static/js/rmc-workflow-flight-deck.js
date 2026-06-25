/**
 * Workflow Flight Deck — operator mission control with retry / apply-fix actions.
 */
(function () {
  "use strict";

  var state = {
    endpoints: {},
    apiUrl: "",
    labels: {},
    loading: false,
    liveSource: null,
    liveRefreshTimer: 0,
    healingTimer: 0,
  };

  var defaultLabels = {
    summary: "Summary",
    active: "Active",
    recent_failures: "Recent failures",
    cross_tenant_signals: "Cross-tenant signals",
    active_count: "Active",
    failed_count: "Recent failures",
    needs_operator_count: "Needs operator",
    healing_count: "Healing",
    no_runs: "No runs.",
    no_incidents: "No correlated incidents.",
    no_actions: "No automated fix available — inspect run detail or Tenant 360.",
    load_error: "Could not load Flight Deck.",
    action_failed: "Action failed",
    runs_label: "runs",
    tenants_label: "tenants",
    bulk_apply_fix: "Apply fix to all eligible runs",
    bulk_apply_progress: "Applying fixes…",
    bulk_apply_done: "Bulk apply finished.",
    action_success: "Action completed.",
    preview_title: "Fix preview",
    live_connected: "Live updates connected",
    healing_mode: "Self-Healing is watching repaired runs",
  };

  function label(key, fallback) {
    if (state.labels && state.labels[key]) return state.labels[key];
    if (defaultLabels[key]) return defaultLabels[key];
    return fallback || key;
  }

  function escapeHtml(v) {
    if (v == null) return "";
    return String(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getCsrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function readEndpoints() {
    var el = document.getElementById("page-data-rmc-flight-deck-endpoints");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (_) {
      return {};
    }
  }

  function readLabels() {
    var el = document.getElementById("page-data-rmc-flight-deck-labels");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (_) {
      return {};
    }
  }

  function endpointFor(kind, run, incident) {
    var base = state.endpoints || {};
    var runId = run.id;
    var schoolId = run.school_id || "";
    if (kind === "apply_fix" || kind === "preview_fix" || kind === "requeue_provision") {
      return (base.apply_fix || "").replace("{run_id}", String(runId));
    }
    if (kind === "cancel") {
      return (base.cancel || "").replace("{run_id}", String(runId));
    }
    if (kind === "requeue_provision_legacy" && schoolId) {
      return (base.requeue_provision || "").replace("{school_id}", String(schoolId));
    }
    if (kind === "bulk_apply_fix") {
      return base.bulk_apply || "";
    }
    return "";
  }

  function renderRemediation(run) {
    var rem = run.suggested_remediation || {};
    var fingerprint = run.error_fingerprint || {};
    var session = run.healing_session || {};
    var diag = session.ai_diagnosis || {};
    var human =
      diag.cause ||
      fingerprint.human_cause ||
      rem.human_action ||
      "";
    if (!human && !(run.error_summary && run.error_summary.message)) {
      return "";
    }
    var err = "";
    if (
      !session.session_id &&
      run.error_summary &&
      run.error_summary.message
    ) {
      err =
        '<div class="rmc-wfp-flight-deck__error small text-danger mt-1">' +
        escapeHtml(run.error_summary.message) +
        "</div>";
    }
    var title = diag.title || fingerprint.human_title || "";
    var titleHtml = title
      ? '<strong class="d-block">' + escapeHtml(title) + "</strong>"
      : "";
    return (
      '<div class="rmc-wfp-flight-deck__remediation mt-2">' +
      titleHtml +
      '<div class="small text-muted">' +
      escapeHtml(human) +
      "</div>" +
      err +
      "</div>"
    );
  }

  function renderHealingPanel(run) {
    var session = run.healing_session || {};
    if (!session.session_id) return "";
    var pct = Number(session.progress_percent || 0);
    var phase = session.phase || "diagnosing";
    var step = session.current_step_label || "Self-healing in progress…";
    var diag = session.ai_diagnosis || {};
    var plan = diag.plan || [];
    var planHtml = "";
    if (plan.length) {
      planHtml = '<ul class="rmc-wfp-flight-deck__healing-plan small mb-2 ps-3">';
      for (var i = 0; i < plan.length; i++) {
        planHtml += "<li>" + escapeHtml(plan[i]) + "</li>";
      }
      planHtml += "</ul>";
    }
    var logs = session.log_lines || [];
    var logHtml = "";
    if (logs.length) {
      logHtml =
        '<div class="rmc-wfp-flight-deck__healing-log small text-muted">';
      for (var j = Math.max(0, logs.length - 4); j < logs.length; j++) {
        logHtml += "<div>" + escapeHtml(logs[j]) + "</div>";
      }
      logHtml += "</div>";
    }
    return (
      '<div class="rmc-wfp-flight-deck__healing mt-2" data-healing-phase="' +
      escapeHtml(phase) +
      '">' +
      '<div class="d-flex justify-content-between align-items-center gap-2 mb-1">' +
      '<span class="small fw-semibold">' +
      escapeHtml(step) +
      "</span>" +
      '<span class="small text-muted">' +
      escapeHtml(String(pct)) +
      "%</span>" +
      "</div>" +
      '<div class="rmc-wfp-flight-deck__healing-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' +
      escapeHtml(String(pct)) +
      '" style="--healing-pct:' +
      escapeHtml(String(Math.max(4, pct))) +
      '%">' +
      '<div class="rmc-wfp-flight-deck__healing-bar-fill"></div>' +
      "</div>" +
      planHtml +
      logHtml +
      "</div>"
    );
  }

  function renderActions(run) {
    var actions = run.operator_actions || [];
    if (!actions.length) {
      return (
        '<p class="rmc-wfp-flight-deck__no-actions small text-muted mb-0 mt-2">' +
        label("no_actions") +
        "</p>"
      );
    }
    var html = '<div class="rmc-wfp-flight-deck__actions mt-2 d-flex flex-wrap gap-2">';
    for (var i = 0; i < actions.length; i++) {
      var action = actions[i];
      var cls = action.primary
        ? "btn btn-sm btn-primary"
        : "btn btn-sm btn-outline-secondary";
      if (action.href) {
        html +=
          '<a class="' +
          cls +
          '" href="' +
          escapeHtml(action.href) +
          '">' +
          escapeHtml(action.label) +
          "</a>";
      } else {
        var capability = action.capability || {};
        var capabilityTag = capability.mode
          ? '<small class="d-block fw-normal text-muted">' +
            escapeHtml(capability.mode === "execute" ? "Executable fix" : capability.mode) +
            "</small>"
          : "";
        var netHint = action.requires_network
          ? '<small class="d-block fw-normal text-muted">Requires network</small>'
          : "";
        html +=
          '<button type="button" class="' +
          cls +
          '" data-rmc-flight-action="' +
          escapeHtml(action.kind) +
          '" data-run-id="' +
          escapeHtml(run.id) +
          '" data-school-id="' +
          escapeHtml(run.school_id || "") +
          '" data-requires-network="' +
          (action.requires_network ? "1" : "0") +
          '">' +
          escapeHtml(action.label) +
          capabilityTag +
          netHint +
          "</button>";
      }
    }
    html += "</div>";
    return html;
  }

  function renderHealingCommand(summary) {
    var healing = summary && summary.healing_count ? Number(summary.healing_count) : 0;
    var live = state.liveSource && state.liveSource.readyState !== 2;
    return (
      '<section class="rmc-wfp-flight-deck__command" aria-live="polite">' +
      '<div class="rmc-wfp-flight-deck__command-copy">' +
      '<span class="rmc-wfp-flight-deck__pulse-dot"></span>' +
      '<strong>Self-Healing cockpit</strong>' +
      '<span>' +
      escapeHtml(live ? label("live_connected") : "Live polling active") +
      "</span>" +
      "</div>" +
      '<div class="rmc-wfp-flight-deck__command-metrics">' +
      '<span><strong>' +
      escapeHtml(summary && summary.stuck_count ? summary.stuck_count : 0) +
      "</strong> stuck</span>" +
      '<span><strong>' +
      escapeHtml(summary && summary.stopped_count ? summary.stopped_count : 0) +
      "</strong> stopped</span>" +
      '<span><strong>' +
      escapeHtml(healing) +
      "</strong> " +
      escapeHtml(label("healing_count")) +
      "</span>" +
      "</div>" +
      "</section>"
    );
  }

  function notify(kind, message) {
    if (
      window.runMyCampusToast &&
      typeof window.runMyCampusToast[kind] === "function"
    ) {
      window.runMyCampusToast[kind](message);
      return;
    }
    if (window.alert) window.alert(message);
  }

  function renderRunContent(run) {
    var statusMeta = run.status_meta || {};
    var displayStatus = run.display_status || statusMeta.label || run.status || "waiting";
    var statusClass = statusMeta.css_class || "rmc-wf-status--" + (run.status || "waiting");
    return (
      '<div class="d-flex flex-wrap justify-content-between align-items-start gap-2">' +
      "<div>" +
      "<strong>" +
      escapeHtml(run.workflow_label || run.workflow_key) +
      "</strong> " +
      '<span class="rmc-wf-status ' +
      escapeHtml(statusClass) +
      '">' +
      escapeHtml(displayStatus) +
      "</span>" +
      '<div class="small text-muted mt-1">' +
      (run.tenant_schema ? escapeHtml(run.tenant_schema) + " · " : "") +
      escapeHtml(run.current_step_name || "") +
      " · " +
      escapeHtml(String(run.progress_percent || 0)) +
      "%</div>" +
      "</div>" +
      "</div>" +
      renderRemediation(run) +
      renderHealingPanel(run) +
      renderActions(run)
    );
  }

  function renderRunRow(run) {
    var statusMeta = run.status_meta || {};
    var dataStatus = statusMeta.key || run.status || "waiting";
    return (
      '<article class="rmc-wfp-flight-deck__run" data-status="' +
      escapeHtml(dataStatus) +
      '" data-run-id="' +
      escapeHtml(run.id) +
      '">' +
      renderRunContent(run) +
      "</article>"
    );
  }

  function renderRunCard(run) {
    var statusMeta = run.status_meta || {};
    var dataStatus = statusMeta.key || run.status || "waiting";
    return (
      '<article class="rmc-wfp-flight-deck__run rmc-wfp-flight-deck__run--card" data-status="' +
      escapeHtml(dataStatus) +
      '" data-run-id="' +
      escapeHtml(run.id) +
      '">' +
      renderRunContent(run) +
      "</article>"
    );
  }

  function renderRuns(title, runs) {
    if (!runs || !runs.length) {
      return (
        '<section class="rmc-wfp-flight-deck__panel">' +
        "<h2>" +
        escapeHtml(title) +
        "</h2>" +
        '<p class="rmc-wfp-flight-deck__empty">' + escapeHtml(label("no_runs")) + "</p></section>"
      );
    }
    var rows = "";
    for (var i = 0; i < runs.length; i++) {
      rows += renderRunRow(runs[i]);
    }
    return (
      '<section class="rmc-wfp-flight-deck__panel">' +
      "<h2>" +
      escapeHtml(title) +
      "</h2>" +
      rows +
      "</section>"
    );
  }

  function renderFailedRuns(title, runs) {
    if (!runs || !runs.length) {
      return (
        '<section class="rmc-wfp-flight-deck__panel rmc-wfp-flight-deck__panel--failures">' +
        "<h2>" +
        escapeHtml(title) +
        "</h2>" +
        '<p class="rmc-wfp-flight-deck__empty">' +
        escapeHtml(label("no_runs")) +
        "</p></section>"
      );
    }
    var cards = "";
    for (var j = 0; j < runs.length; j++) {
      cards += renderRunCard(runs[j]);
    }
    return (
      '<section class="rmc-wfp-flight-deck__panel rmc-wfp-flight-deck__panel--failures">' +
      "<h2>" +
      escapeHtml(title) +
      "</h2>" +
      '<div class="rmc-wfp-flight-deck__run-grid">' +
      cards +
      "</div></section>"
    );
  }

  function renderSummary(summary) {
    if (!summary) return "";
    return (
      '<section class="rmc-wfp-flight-deck__panel rmc-wfp-flight-deck__panel--summary">' +
      "<h2>" + escapeHtml(label("summary")) + "</h2>" +
      '<ul class="list-unstyled small mb-0">' +
      "<li>" + escapeHtml(label("active_count")) + ": " +
      escapeHtml(summary.active_count || 0) +
      "</li>" +
      "<li>" + escapeHtml(label("failed_count")) + ": " +
      escapeHtml(summary.failed_count || 0) +
      "</li>" +
      "<li>" + escapeHtml(label("needs_operator_count")) + ": " +
      escapeHtml(summary.needs_operator_count || 0) +
      "</li>" +
      "</ul></section>"
    );
  }

  function renderIncidentActions(inc) {
    var actions = inc.operator_actions || [];
    if (!actions.length) return "";
    var html = '<div class="rmc-wfp-flight-deck__actions mt-2 d-flex flex-wrap gap-2">';
    for (var i = 0; i < actions.length; i++) {
      var action = actions[i];
      html +=
        '<button type="button" class="btn btn-sm btn-primary" data-rmc-flight-action="' +
        escapeHtml(action.kind) +
        '" data-remediation-key="' +
        escapeHtml(action.remediation_key || inc.remediation_key || "") +
        '">' +
        escapeHtml(action.label || label("bulk_apply_fix")) +
        "</button>";
    }
    html += "</div>";
    return html;
  }

  function renderIncidents(incidents) {
    if (!incidents || !incidents.length) {
      return (
        '<section class="rmc-wfp-flight-deck__panel">' +
        "<h2>" + escapeHtml(label("cross_tenant_signals")) + "</h2>" +
        '<p class="rmc-wfp-flight-deck__empty">' + escapeHtml(label("no_incidents")) + "</p></section>"
      );
    }
    var html =
      '<section class="rmc-wfp-flight-deck__panel"><h2>' +
      escapeHtml(label("cross_tenant_signals")) +
      "</h2>";
    for (var j = 0; j < incidents.length; j++) {
      var inc = incidents[j];
      html +=
        '<div class="rmc-wfp-flight-deck__incident">' +
        "<strong>" +
        escapeHtml(inc.remediation_key) +
        "</strong> — " +
        escapeHtml(inc.run_count) +
        " " +
        escapeHtml(label("runs_label")) +
        " / " +
        escapeHtml(inc.tenant_count) +
        " " +
        escapeHtml(label("tenants_label")) +
        '<br><span class="small text-muted">' +
        escapeHtml(inc.sample_action || "") +
        "</span>" +
        renderIncidentActions(inc) +
        "</div>";
    }
    html += "</section>";
    return html;
  }

  function pushCopilotContext(ctx) {
    if (!ctx) return;
    window.__rmcWorkflowCopilotContext = ctx;
    document.dispatchEvent(
      new CustomEvent("rmc-workflow-copilot-context", { detail: ctx })
    );
  }

  function findRunById(runId) {
    var card = document.querySelector(
      '.rmc-wfp-flight-deck__run[data-run-id="' + runId + '"]'
    );
    return card;
  }

  function postAction(url, options) {
    options = options || {};
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        Accept: "application/json",
        "Content-Type": options.contentType || "application/x-www-form-urlencoded",
      },
      body: options.body || "",
    }).then(function (r) {
      var ct = (r.headers.get("content-type") || "").toLowerCase();
      if (ct.indexOf("application/json") === -1) {
        return r.text().then(function (text) {
          return {
            ok: false,
            status: r.status,
            json: {
              ok: false,
              reason: "non_json_response",
              message: (text || "").slice(0, 200),
            },
          };
        });
      }
      return r.json().then(function (j) {
        return { ok: r.ok, status: r.status, json: j };
      });
    });
  }

  function handleActionClick(evt) {
    var btn = evt.currentTarget;
    var kind = btn.getAttribute("data-rmc-flight-action");
    if (
      btn.getAttribute("data-requires-network") === "1" &&
      typeof navigator !== "undefined" &&
      navigator.onLine === false
    ) {
      notify(
        "gentle",
        label("action_requires_network") || "Requires network — retry when connected"
      );
      return;
    }
    var runId = btn.getAttribute("data-run-id");
    var remediationKey = btn.getAttribute("data-remediation-key") || "";
    if (!kind) return;
    btn.disabled = true;
    var run = { id: runId, school_id: btn.getAttribute("data-school-id") || "" };

    if (kind === "bulk_apply_fix") {
      var bulkUrl = endpointFor(kind, run);
      if (!bulkUrl) {
        btn.disabled = false;
        return;
      }
      postAction(bulkUrl, {
        body: "remediation_key=" + encodeURIComponent(remediationKey),
      })
        .then(function (result) {
          if (result.json && (result.json.ok || result.json.applied)) {
            scheduleHealingRefresh(result.json.healing_poll_ms || 2500);
            notify("success", label("bulk_apply_done"));
            return;
          }
          var err =
            (result.json && (result.json.reason || result.json.error)) ||
            label("action_failed");
          notify("gentle", String(err));
          btn.disabled = false;
        })
        .catch(function () {
          btn.disabled = false;
        });
      return;
    }

    if (!runId) {
      notify(
        "gentle",
        label("action_unavailable", "This action isn't available for this run.")
      );
      btn.disabled = false;
      return;
    }

    var url = endpointFor(kind, run);
    if (!url) {
      // No resolvable endpoint (e.g. a provisioning run with no school_id) — tell
      // the operator instead of silently re-enabling a button that looks dead.
      notify(
        "gentle",
        label("action_unavailable", "This action isn't available for this run.")
      );
      btn.disabled = false;
      return;
    }

    var promise;
    if (kind === "preview_fix") {
      promise = postAction(url + (url.indexOf("?") >= 0 ? "&" : "?") + "dry_run=1");
    } else {
      promise = postAction(url);
    }

    promise
      .then(function (result) {
        if (kind === "preview_fix" && result.json) {
          var note =
            result.json.note ||
            result.json.would_apply ||
            JSON.stringify(result.json);
          notify("info", label("preview_title") + ": " + String(note));
          btn.disabled = false;
          return;
        }
        if (result.json && result.json.ok) {
          var row = findRunById(runId);
          if (row) {
            row.classList.add("rmc-wfp-flight-deck__run--acted");
            row.setAttribute("data-status", "healing");
            row.setAttribute("aria-busy", "true");
          }
          notify("success", result.json.operator_message || label("action_success"));
          scheduleHealingRefresh(result.json.healing_poll_ms || 2500);
          return;
        }
        var err =
          (result.json &&
            (result.json.reason || result.json.error || result.json.message)) ||
          label("action_failed");
        notify("gentle", String(err));
        btn.disabled = false;
      })
      .catch(function () {
        // Network-level failure (fetch rejected) — e.g. the web service is 502ing
        // / restarting. Without this the button just silently re-enabled, which is
        // exactly the "I click it and nothing happens" symptom during an outage.
        notify(
          "gentle",
          label(
            "action_unreachable",
            "Couldn't reach the server — it may be restarting. Try again in a moment."
          )
        );
        btn.disabled = false;
      });
  }

  function wireActions(root) {
    var buttons = root.querySelectorAll("[data-rmc-flight-action]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", handleActionClick);
    }
  }

  function scheduleLoad(delay) {
    window.clearTimeout(state.liveRefreshTimer);
    state.liveRefreshTimer = window.setTimeout(loadDeck, delay || 250);
  }

  function scheduleHealingRefresh(intervalMs) {
    var delays = [500, intervalMs || 2500, 6500, 12000];
    for (var i = 0; i < delays.length; i++) {
      window.setTimeout(loadDeck, delays[i]);
    }
    window.clearTimeout(state.healingTimer);
    state.healingTimer = window.setInterval(loadDeck, Math.max(intervalMs || 2500, 2500));
    window.setTimeout(function () {
      window.clearInterval(state.healingTimer);
    }, 45000);
  }

  function loadDeck() {
    var root = document.getElementById("rmc-wfp-flight-deck");
    if (!root) return;
    if (state.loading) return;
    state.loading = true;
    fetch(state.apiUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.endpoints) state.endpoints = data.endpoints;
        if (data.labels) state.labels = data.labels;
        root.innerHTML =
          renderHealingCommand(data.summary) +
          '<div class="rmc-wfp-flight-deck__top">' +
          renderSummary(data.summary) +
          renderRuns(label("active"), data.active) +
          "</div>" +
          renderFailedRuns(label("recent_failures"), data.recent_failed) +
          renderIncidents(data.incidents);
        wireActions(root);
        pushCopilotContext(data.copilot_context);
        state.loading = false;
      })
      .catch(function () {
        root.innerHTML =
          '<p class="rmc-wfp-flight-deck__empty">' + escapeHtml(label("load_error")) + "</p>";
        state.loading = false;
      });
  }

  function connectLiveStream() {
    if (!window.EventSource || !state.endpoints || !state.endpoints.stream) return;
    try {
      if (state.liveSource) state.liveSource.close();
      state.liveSource = new EventSource(state.endpoints.stream);
      state.liveSource.addEventListener("snapshot", function () {
        scheduleLoad(300);
      });
      state.liveSource.addEventListener("bye", function () {
        if (state.liveSource) state.liveSource.close();
        state.liveSource = null;
        window.setTimeout(connectLiveStream, 2500);
      });
      state.liveSource.onerror = function () {
        if (state.liveSource) state.liveSource.close();
        state.liveSource = null;
        window.setTimeout(connectLiveStream, 8000);
      };
    } catch (_) {
      state.liveSource = null;
    }
  }

  function mount() {
    var root = document.getElementById("rmc-wfp-flight-deck");
    if (!root) return;
    state.apiUrl =
      root.getAttribute("data-api-url") ||
      "/platform-runtime/workflow-progress/flight-deck.json";
    state.endpoints = readEndpoints();
    state.labels = readLabels();
    loadDeck();
    connectLiveStream();
    var refreshBtn = document.getElementById("rmc-wfp-flight-deck-refresh");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", function () {
        loadDeck();
      });
    }
    window.setInterval(loadDeck, 10000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
