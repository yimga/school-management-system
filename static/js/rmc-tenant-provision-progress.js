/**
 * Customer-facing tenant provisioning progress (workflow-driven bar + steps).
 * Polls canonical provisioning API; updates DOM without full page reload.
 * Updates aria-valuenow on [data-rmc-provision-bar] and .rmc-provision-progress__fill width.
 */
(function () {
  "use strict";

  var roots = document.querySelectorAll("[data-rmc-provision-progress]");
  if (!roots.length) return;

  var POLL_MS = 3000;

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function stepClass(state) {
    if (state === "done") return "rmc-wfp-step--done";
    if (state === "active") return "rmc-wfp-step--active";
    if (state === "failed") return "rmc-wfp-step--failed";
    return "rmc-wfp-step--pending";
  }

  function mount(root) {
    var api = root.getAttribute("data-rmc-provisioning-api");
    if (!api) return;

    var bar = root.querySelector("[data-rmc-provision-bar]");
    var fill =
      root.querySelector(".rmc-provision-progress__fill") ||
      root.querySelector("[data-rmc-provision-fill]");
    var pctEl = root.querySelector("[data-rmc-provision-pct]");
    var stepEl = root.querySelector("[data-rmc-provision-step]");
    var stepsOl = root.querySelector("[data-rmc-provision-steps]");
    var labelEl = root.querySelector("[data-rmc-provision-label]");
    var errPanel = root.querySelector("[data-rmc-provision-error-panel]");
    var errText = root.querySelector("[data-rmc-provision-error-text]");
    var retryBtn = root.querySelector("[data-rmc-provision-retry]");
    var askBtn = root.querySelector("[data-rmc-provision-ask-assistant]");
    var applyFixUrl = root.getAttribute("data-rmc-provision-apply-fix") || "";
    var dashboardHref =
      root.getAttribute("data-rmc-provision-dashboard-href") || "";
    var redirected = false;

    function updateCopilotContext(data) {
      var ctx = {
        surface: "tenant_provision",
        workflow_key: data.workflow_key || "",
        workflow_run_id: data.workflow_run_id || null,
        current_step: data.current_step_key || "",
        last_error: data.last_error || "",
        progress_percent: data.progress_percent || 0,
      };
      root.setAttribute("data-rmc-copilot-context", JSON.stringify(ctx));
    }

    function renderSteps(steps) {
      if (!stepsOl || !steps || !steps.length) return;
      stepsOl.hidden = false;
      stepsOl.innerHTML = steps
        .map(function (s) {
          return (
            '<li class="rmc-wfp-step ' +
            stepClass(s.state) +
            '"><span class="rmc-wfp-step__label">' +
            escapeHtml(s.label || s.key) +
            "</span></li>"
          );
        })
        .join("");
    }

    function applyPayload(data) {
      if (!data || !data.ok) return;

      var pct = parseInt(data.progress_percent, 10);
      if (isNaN(pct)) pct = 0;
      pct = Math.max(0, Math.min(100, pct));

      if (fill) fill.style.width = pct + "%";
      if (bar) bar.setAttribute("aria-valuenow", String(pct));
      if (pctEl) pctEl.textContent = pct + "%";

      var stepLabel =
        data.current_step_label ||
        (data.unified && data.unified.label) ||
        "";
      if (stepEl && stepLabel) stepEl.textContent = stepLabel;

      if (labelEl && data.status === "failed") {
        labelEl.textContent = "Setup paused";
      } else if (labelEl && (data.portal_ready || data.is_active)) {
        labelEl.textContent = "Portal ready";
      }

      renderSteps(data.steps || []);
      updateCopilotContext(data);

      var failed = data.status === "failed";
      var remediation = data.suggested_remediation || {};
      if (errPanel && errText) {
        if (failed && (data.last_error || remediation.human_action)) {
          errPanel.classList.remove("d-none");
          errText.textContent =
            data.last_error || remediation.human_action || "";
        } else {
          errPanel.classList.add("d-none");
          errText.textContent = "";
        }
      }
      if (retryBtn) {
        if (failed && remediation.owner_may_apply && remediation.auto_fix_kind) {
          retryBtn.classList.remove("d-none");
          retryBtn.setAttribute("data-auto-fix-kind", remediation.auto_fix_kind);
        } else {
          retryBtn.classList.add("d-none");
        }
      }

      var ready = data.portal_ready === true || data.is_active === true;
      if (ready) {
        var actionsEl = document.getElementById("rmc-provision-complete-actions");
        if (actionsEl) {
          actionsEl.hidden = false;
        }
        var loginBtn = document.querySelector("[data-rmc-provision-login]");
        var tenantLogin = data.tenant_login_url || "";
        if (loginBtn && tenantLogin) {
          loginBtn.setAttribute("href", tenantLogin);
        }
        if (!redirected) {
          var href = data.dashboard_href || dashboardHref;
          if (href && data.status === "succeeded") {
            redirected = true;
            window.setTimeout(function () {
              window.location.href = href;
            }, 1200);
          }
        }
      }
    }

    function poll() {
      fetch(api, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          return r.json();
        })
        .then(applyPayload)
        .catch(function () {});
    }

    if (retryBtn && applyFixUrl) {
      retryBtn.addEventListener("click", function () {
        var kind = retryBtn.getAttribute("data-auto-fix-kind") || "";
        if (!kind) return;
        var body = new URLSearchParams();
        body.set("auto_fix_kind", kind);
        fetch(applyFixUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": getCsrfToken(),
          },
          body: body.toString(),
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (res) {
            if (res && res.ok) poll();
          })
          .catch(function () {});
      });
    }

    if (askBtn) {
      askBtn.addEventListener("click", function () {
        var ctxRaw = root.getAttribute("data-rmc-copilot-context") || "{}";
        var prompt = "Help me understand my school setup status.";
        try {
          var ctx = JSON.parse(ctxRaw);
          if (ctx.last_error) {
            prompt =
              "My school setup failed at step " +
              (ctx.current_step || "unknown") +
              ": " +
              ctx.last_error +
              ". What should I do next?";
          }
        } catch (e) {
          /* use default prompt */
        }
        document.dispatchEvent(
          new CustomEvent("rmc-copilot-open", {
            detail: { prompt: prompt, surface: "tenant_provision" },
          })
        );
      });
    }

    poll();
    window.setInterval(poll, POLL_MS);
  }

  roots.forEach(mount);
})();
