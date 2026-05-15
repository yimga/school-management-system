/* RMC Friction recorder (Wave B — G5).
 *
 * Captures "stuck user" signals from the browser and POSTs them to
 * /api/observability/friction/. Hard-debounced + capped per session so a
 * misbehaving form does not flood the endpoint.
 *
 * Kinds:
 *   validation_retry — form submitted with errors >= 3 times
 *   form_abandon     — user started a form, dwelled >60s, left without submit
 *   repeat_error     — same client-side error message fired 3x in a session
 *
 * Listen-only by default; pages opt out by setting
 *   `window.RMC_FRICTION_DISABLED = true`
 * before this script loads (e.g. on the friction-debug page itself).
 */
(function () {
  "use strict";

  if (window.RMC_FRICTION_DISABLED) {
    return;
  }

  var INGEST_URL = "/api/observability/friction/";
  var DWELL_MS = 60_000;
  var VALIDATION_RETRY_THRESHOLD = 3;
  var REPEAT_ERROR_THRESHOLD = 3;
  var MAX_REPORTS_PER_KIND = 4;

  function getViewName() {
    // Stable per-page identifier — prefer the rmc-shell-root + first path
    // segment; fall back to pathname.
    var root = document.documentElement.getAttribute("data-rmc-shell-root") || "";
    var path = (location.pathname || "").split("/").filter(Boolean).slice(0, 2).join(".") || "root";
    return root ? root + ":" + path : path;
  }

  function getCsrfToken() {
    var match = (document.cookie || "").match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  var reportCounts = Object.create(null);
  function shouldReport(kind) {
    var n = (reportCounts[kind] || 0) + 1;
    reportCounts[kind] = n;
    return n <= MAX_REPORTS_PER_KIND;
  }

  function report(kind, payload) {
    if (!shouldReport(kind)) return;
    try {
      var body = JSON.stringify({
        view_name: getViewName(),
        kind: kind,
        payload: payload || {},
      });
      // Prefer sendBeacon for pagehide reliability.
      if (kind === "form_abandon" && navigator.sendBeacon) {
        navigator.sendBeacon(INGEST_URL, new Blob([body], { type: "application/json" }));
        return;
      }
      fetch(INGEST_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: body,
        keepalive: true,
      }).catch(function () { /* never let telemetry crash the page */ });
    } catch (_err) { /* noop */ }
  }

  // --- validation_retry ----------------------------------------------------
  // Track per-form invalid-submit counts. We can't know server-side validation
  // failures without parsing the response, so we count `:invalid` form-element
  // submits (HTML5 constraints) plus explicit `.is-invalid` / `.rmc-form-field__error`
  // classes set after a server roundtrip.
  var invalidCounts = new WeakMap();
  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!form || form.tagName !== "FORM") return;
      // Wait a tick so server-rendered error classes can paint.
      window.setTimeout(function () {
        var hasInvalid =
          !form.checkValidity() ||
          form.querySelector(".is-invalid, .rmc-form-field__error, [aria-invalid='true']");
        if (!hasInvalid) return;
        var n = (invalidCounts.get(form) || 0) + 1;
        invalidCounts.set(form, n);
        if (n >= VALIDATION_RETRY_THRESHOLD) {
          var fields = Array.prototype.slice
            .call(form.querySelectorAll("[name]"), 0, 10)
            .map(function (el) { return el.getAttribute("name"); });
          report("validation_retry", { retry_count: n, fields: fields });
          invalidCounts.set(form, 0); // reset so repeat reports require fresh sequence
        }
      }, 50);
    },
    true,
  );

  // --- form_abandon --------------------------------------------------------
  // Mark a form "touched" on first user input, then if pagehide fires with
  // dwell >= 60s and no successful submit, report.
  var touchedAt = new WeakMap();
  var submitted = new WeakSet();
  document.addEventListener(
    "input",
    function (event) {
      var form = event.target && event.target.form;
      if (form && !touchedAt.has(form)) touchedAt.set(form, Date.now());
    },
    true,
  );
  document.addEventListener(
    "submit",
    function (event) {
      if (event.target && event.target.tagName === "FORM") submitted.add(event.target);
    },
    true,
  );
  window.addEventListener("pagehide", function () {
    var forms = document.querySelectorAll("form");
    for (var i = 0; i < forms.length; i++) {
      var form = forms[i];
      var ts = touchedAt.get(form);
      if (!ts || submitted.has(form)) continue;
      var dwell = Date.now() - ts;
      if (dwell >= DWELL_MS) {
        report("form_abandon", {
          dwell_ms: dwell,
          field_count: form.querySelectorAll("[name]").length,
        });
      }
    }
  });

  // --- repeat_error --------------------------------------------------------
  var errorCounts = Object.create(null);
  window.addEventListener("error", function (event) {
    if (!event || !event.message) return;
    var key = String(event.message).slice(0, 200);
    var n = (errorCounts[key] || 0) + 1;
    errorCounts[key] = n;
    if (n === REPEAT_ERROR_THRESHOLD) {
      report("repeat_error", {
        message: key,
        filename: String(event.filename || "").slice(0, 200),
      });
    }
  });

  // Expose a small surface for tests / debugging.
  var ns = (window.RMC = window.RMC || {});
  ns.friction = {
    report: report,
    _reset: function () {
      reportCounts = Object.create(null);
      errorCounts = Object.create(null);
    },
  };
})();
