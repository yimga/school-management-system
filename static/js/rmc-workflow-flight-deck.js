/**
 * Workflow Flight Deck — loads flight-deck.json and paints mission control panels.
 */
(function () {
  "use strict";

  function escapeHtml(v) {
    if (v == null) return "";
    return String(v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderRuns(title, runs) {
    if (!runs || !runs.length) {
      return (
        '<section class="rmc-wfp-flight-deck__panel">' +
        "<h2>" + escapeHtml(title) + "</h2>" +
        '<p class="rmc-wfp-flight-deck__empty">No runs.</p></section>'
      );
    }
    var rows = "";
    for (var i = 0; i < runs.length; i++) {
      var r = runs[i];
      rows +=
        '<div class="rmc-wfp-flight-deck__run" data-status="' +
        escapeHtml(r.status) +
        '">' +
        "<strong>" +
        escapeHtml(r.workflow_label || r.workflow_key) +
        "</strong> " +
        '<span class="badge text-bg-secondary">' +
        escapeHtml(r.status) +
        "</span>" +
        '<div class="small text-muted">' +
        escapeHtml(r.current_step_name || "") +
        " · " +
        escapeHtml(String(r.progress_percent || 0)) +
        "%</div></div>";
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

  function renderIncidents(incidents) {
    if (!incidents || !incidents.length) {
      return (
        '<section class="rmc-wfp-flight-deck__panel">' +
        "<h2>Cross-tenant signals</h2>" +
        '<p class="rmc-wfp-flight-deck__empty">No correlated incidents.</p></section>'
      );
    }
    var html = '<section class="rmc-wfp-flight-deck__panel"><h2>Cross-tenant signals</h2>';
    for (var j = 0; j < incidents.length; j++) {
      var inc = incidents[j];
      html +=
        '<div class="rmc-wfp-flight-deck__incident">' +
        "<strong>" +
        escapeHtml(inc.remediation_key) +
        "</strong> — " +
        escapeHtml(inc.run_count) +
        " runs / " +
        escapeHtml(inc.tenant_count) +
        ' tenants<br><span class="small text-muted">' +
        escapeHtml(inc.sample_action || "") +
        "</span></div>";
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

  function mount() {
    var root = document.getElementById("rmc-wfp-flight-deck");
    if (!root) return;
    var url = root.getAttribute("data-api-url") || "/platform-runtime/workflow-progress/flight-deck.json";
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        root.innerHTML =
          renderRuns("Active", data.active) +
          renderRuns("Recent failures", data.recent_failed) +
          renderIncidents(data.incidents);
        pushCopilotContext(data.copilot_context);
      })
      .catch(function () {
        root.innerHTML =
          '<p class="rmc-wfp-flight-deck__empty">Could not load Flight Deck.</p>';
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
