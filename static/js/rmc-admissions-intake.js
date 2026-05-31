/**
 * rmc-admissions-intake.js — v4.00.35 (2026-05-29)
 *
 * Auto-renderer for the country/system-type-aware admissions intake schema.
 * Any element with `data-rmc-admissions-intake="1"` will be populated with
 * a per-subject <fieldset> driven by the tenant's resolved exam schema.
 *
 * v4.00.35: when the rendered fieldset is inside a <form>, the script also
 * attaches a submit-time hook that POSTs `{applicant_id, exam_scores,
 * exam_marker, exam_schema_code}` to `/api/v1/admissions/applicant-scores/`
 * if the form carries `data-rmc-intake-auto-post="1"` AND a hidden
 * `applicant_id` field is present. The native form still submits — the
 * auto-POST runs first as a best-effort capture and never blocks the
 * surrounding form lifecycle.
 *
 * Markup contract (operator side):
 *   <div data-rmc-admissions-intake="1"
 *        data-name-prefix="exam_score_"
 *        data-required="true"></div>
 *
 * What it does:
 *   1. GET /api/v1/admissions/intake-schema/
 *   2. If a schema is returned, render label + select per subject
 *   3. Emit a hidden input `exam_marker` with the schema code so the
 *      server can persist + reason about which exam was captured
 *   4. Operator override via ?country=GH&type=shs query string (already
 *      supported by the API; we just forward the URL search params)
 *
 * Insert-only, idempotent, silent on miss (no console spam).
 */
(function () {
  "use strict";

  function intakeSchemaUrl() {
    return (window.RMCPlatformSurface && window.RMCPlatformSurface.url("admissions_intake_schema")) || "";
  }
  function applicantScoresUrl() {
    return (window.RMCPlatformSurface && window.RMCPlatformSurface.url("admissions_applicant_scores")) || "";
  }

  function mountRoot(root) {
    if (!root || root.getAttribute("data-rmc-intake-mounted") === "1") return;
    root.setAttribute("data-rmc-intake-mounted", "1");

    var prefix = root.getAttribute("data-name-prefix") || "exam_score_";
    var required = (root.getAttribute("data-required") || "").toLowerCase() === "true";
    var preview = root.getAttribute("data-preview-country") || "";
    var previewType = root.getAttribute("data-preview-type") || "";

    var qs = [];
    if (preview) qs.push("country=" + encodeURIComponent(preview));
    if (previewType) qs.push("type=" + encodeURIComponent(previewType));
    var base = intakeSchemaUrl();
    if (!base) return;
    var url = base + (qs.length ? (base.indexOf("?") >= 0 ? "&" : "?") + qs.join("&") : "");

    fetch(url, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" }
    }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j || !j.schema || !j.field_specs || !j.field_specs.length) {
        return; // No schema for this tenant — leave the container empty
      }
      renderSchema(root, j, prefix, required);
    }).catch(function () { /* silent */ });
  }

  function renderSchema(root, payload, prefix, required) {
    var schema = payload.schema;
    var fieldSpecs = payload.field_specs;

    // Wipe any prior content (the API is the single source of truth).
    root.textContent = "";

    var legend = document.createElement("div");
    legend.className = "rmc-intake__legend";
    legend.innerHTML =
      '<div class="rmc-intake__legend-title">' + escapeHtml(schema.label || "Exam scores") + '</div>' +
      (schema.notes ? '<div class="rmc-intake__legend-notes">' + escapeHtml(schema.notes) + '</div>' : '');
    root.appendChild(legend);

    // Hidden inputs that preserve the schema identity server-side.
    var hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "exam_marker";
    hidden.value = schema.exam_marker || schema.code || "";
    root.appendChild(hidden);

    var schemaCode = document.createElement("input");
    schemaCode.type = "hidden";
    schemaCode.name = "exam_schema_code";
    schemaCode.value = schema.code || "";
    root.appendChild(schemaCode);

    var grid = document.createElement("div");
    grid.className = "rmc-intake__grid";

    fieldSpecs.forEach(function (spec) {
      var row = document.createElement("div");
      row.className = "rmc-intake__field";
      var inputId = "rmc-intake-" + spec.name;
      var label = document.createElement("label");
      label.className = "rmc-intake__label";
      label.setAttribute("for", inputId);
      label.textContent = spec.label || spec.name;
      if (required) {
        var star = document.createElement("span");
        star.className = "rmc-intake__required";
        star.setAttribute("aria-hidden", "true");
        star.textContent = " *";
        label.appendChild(star);
      }
      row.appendChild(label);

      var select = document.createElement("select");
      select.id = inputId;
      select.name = prefix + spec.name.replace(/^score_/, "");
      select.className = "rmc-intake__select form-select";
      if (required) select.required = true;

      var placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "—";
      select.appendChild(placeholder);

      (spec.choices || []).forEach(function (choice) {
        var opt = document.createElement("option");
        opt.value = String(choice);
        opt.textContent = String(choice);
        select.appendChild(opt);
      });

      row.appendChild(select);
      grid.appendChild(row);
    });

    root.appendChild(grid);

    // v4.00.35 — wire optional auto-POST hook on the enclosing form.
    wireAutoPost(root, schema, prefix);

    // Dispatch a custom event so calling pages can react (e.g. show
    // "score required" hint, refresh a totals widget, etc.)
    try {
      root.dispatchEvent(new CustomEvent("rmc:admissions-intake:ready", {
        bubbles: true,
        detail: { schema: schema, field_count: fieldSpecs.length }
      }));
    } catch (_) { /* IE noop */ }
  }

  function wireAutoPost(root, schema, prefix) {
    // Find the enclosing <form> + check the opt-in flag.
    var form = root.closest ? root.closest("form") : null;
    if (!form) return;
    if ((form.getAttribute("data-rmc-intake-auto-post") || "").toLowerCase() !== "1") return;
    if (form.getAttribute("data-rmc-intake-autopost-wired") === "1") return;
    form.setAttribute("data-rmc-intake-autopost-wired", "1");

    form.addEventListener("submit", function () {
      try {
        var applicantField = form.querySelector('input[name="applicant_id"]');
        if (!applicantField || !applicantField.value) return;

        var scores = {};
        form.querySelectorAll('[name^="' + prefix + '"]').forEach(function (el) {
          var subject = el.name.substring(prefix.length);
          if (subject && el.value) scores[subject] = el.value;
        });

        var body = new FormData();
        body.append("applicant_id", applicantField.value);
        body.append("exam_marker", schema.exam_marker || schema.code || "");
        body.append("exam_schema_code", schema.code || "");
        body.append("exam_scores_json", JSON.stringify(scores));
        var csrf = (form.querySelector('input[name="csrfmiddlewaretoken"]') || {}).value;
        if (csrf) body.append("csrfmiddlewaretoken", csrf);

        // Best-effort fire-and-forget. We DO NOT await this — the form's
        // own submit handler still runs as normal.
        if (navigator.sendBeacon) {
          // sendBeacon doesn't include csrfmiddlewaretoken header, so fall
          // back to keepalive fetch when we need CSRF.
          var scoresUrl = applicantScoresUrl();
          if (!scoresUrl) return;
          fetch(scoresUrl, {
            method: "POST",
            credentials: "same-origin",
            body: body,
            keepalive: true,
            headers: { "X-Requested-With": "XMLHttpRequest" }
          }).catch(function () { /* silent */ });
        } else {
          var scoresUrlFallback = applicantScoresUrl();
          if (!scoresUrlFallback) return;
          fetch(scoresUrlFallback, {
            method: "POST",
            credentials: "same-origin",
            body: body,
            headers: { "X-Requested-With": "XMLHttpRequest" }
          }).catch(function () { /* silent */ });
        }
      } catch (_) { /* silent */ }
    }, { capture: true });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c];
    });
  }

  function bootAll() {
    var nodes = document.querySelectorAll('[data-rmc-admissions-intake="1"]');
    for (var i = 0; i < nodes.length; i++) mountRoot(nodes[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootAll);
  } else {
    bootAll();
  }

  // Expose for late-mounting (HTMX swaps, modal opens, etc.)
  window.rmcAdmissionsIntake = { mount: mountRoot, mountAll: bootAll };
})();
