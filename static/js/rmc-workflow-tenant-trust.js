/**
 * Tenant-trusted workflow strip — polls tenant-safe active runs (wave 4).
 */
(function () {
  "use strict";

  var ENDPOINT = "/platform-runtime/workflow-progress/tenant-trusted/active/";
  var POLL_MS = 8000;

  function mount() {
    var root = document.querySelector("[data-rmc-wfp-tenant-trust]");
    if (!root) return;

    function paint(runs) {
      if (!runs || !runs.length) {
        root.hidden = true;
        return;
      }
      var body = root.querySelector("[data-rmc-wfp-tenant-trust-body]");
      if (!body) return;
      var parts = [];
      for (var i = 0; i < Math.min(runs.length, 3); i++) {
        var r = runs[i];
        parts.push(
          (r.workflow_label || r.workflow_key) +
            " — " +
            (r.current_step_name || r.status) +
            " (" +
            (r.progress_percent || 0) +
            "%)"
        );
      }
      body.textContent = parts.join(" · ");
      root.hidden = false;
    }

    function poll() {
      fetch(ENDPOINT, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          if (data && data.runs) paint(data.runs);
        })
        .catch(function () {});
    }

    poll();
    window.setInterval(poll, POLL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
