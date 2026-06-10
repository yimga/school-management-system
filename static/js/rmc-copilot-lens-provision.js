/**
 * Operator copilot Lens — live provisioning mini-train + requeue CTA.
 * Polls GET /super/api/schools/<id>/lens/ when row detail includes lensApiUrl.
 */
(function () {
  "use strict";

  if (typeof document === "undefined") { return; }

  var POLL_MS = 5000;
  var pollTimer = null;
  var activeLensUrl = "";
  var activeRequeueUrl = "";
  var pollInFlight = false;

  function lensRoots() {
    return document.querySelectorAll("[data-rmc-copilot-lens-root]");
  }

  function getCsrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) { return input.value; }
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function escapeHtml(value) {
    if (value === null || value === undefined) { return ""; }
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function stepClass(state) {
    if (state === "done") { return "lx-copilot__lens-provision-step--done"; }
    if (state === "active") { return "lx-copilot__lens-provision-step--active"; }
    if (state === "failed") { return "lx-copilot__lens-provision-step--failed"; }
    return "lx-copilot__lens-provision-step--pending";
  }

  function clearPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    activeLensUrl = "";
    activeRequeueUrl = "";
    pollInFlight = false;
    lensRoots().forEach(function (root) {
      var block = root.querySelector("[data-rmc-copilot-lens-provision]");
      if (block) { block.hidden = true; }
    });
  }

  function renderHealthChips(root, chips) {
    var host = root.querySelector("[data-rmc-copilot-lens-status]");
    if (!host || !chips || !chips.length) { return; }
    host.innerHTML = "";
    chips.forEach(function (chip) {
      if (!chip) { return; }
      var span = document.createElement("span");
      span.className =
        "lx-copilot__lens-pill lx-copilot__lens-pill--" +
        (chip.tone || "muted");
      span.textContent = (chip.label || chip.key || "") + ": " + (chip.value || "—");
      host.appendChild(span);
    });
    host.hidden = false;
  }

  function renderProvision(root, payload) {
    if (!payload) { return; }
    renderHealthChips(root, payload.health_chips || []);

    var prov = payload.provisioning;
    var block = root.querySelector("[data-rmc-copilot-lens-provision]");
    if (!block) { return; }

    if (!prov || (prov.portal_ready && prov.status === "succeeded")) {
      block.hidden = true;
      return;
    }

    block.hidden = false;
    var pctEl = block.querySelector("[data-rmc-copilot-lens-provision-pct]");
    if (pctEl) {
      pctEl.textContent = String(prov.progress_percent || 0) + "%";
    }

    var stepsOl = block.querySelector("[data-rmc-copilot-lens-provision-steps]");
    var steps = prov.extended_steps || [];
    if (stepsOl) {
      stepsOl.innerHTML = "";
      steps.forEach(function (step) {
        if (!step) { return; }
        var li = document.createElement("li");
        li.className =
          "lx-copilot__lens-provision-step " + stepClass(step.state || "pending");
        li.innerHTML =
          '<span class="lx-copilot__lens-provision-step__dot" aria-hidden="true"></span>' +
          '<span class="lx-copilot__lens-provision-step__label">' +
          escapeHtml(step.label || step.key || "") +
          "</span>";
        stepsOl.appendChild(li);
      });
    }

    var errEl = block.querySelector("[data-rmc-copilot-lens-provision-error]");
    if (errEl) {
      if (prov.last_error) {
        errEl.textContent = String(prov.last_error);
        errEl.hidden = false;
      } else {
        errEl.textContent = "";
        errEl.hidden = true;
      }
    }

    var requeueBtn = block.querySelector("[data-rmc-copilot-lens-requeue]");
    if (requeueBtn) {
      requeueBtn.hidden = !prov.can_requeue;
      requeueBtn.disabled = false;
    }
  }

  function shouldKeepPolling(payload) {
    if (!payload || !payload.provisioning) { return false; }
    var prov = payload.provisioning;
    if (prov.portal_ready) { return false; }
    var status = (prov.status || "").toLowerCase();
    return status === "running" || status === "unknown" || !status;
  }

  function fetchLens() {
    if (!activeLensUrl || pollInFlight) { return; }
    pollInFlight = true;
    fetch(activeLensUrl, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        if (!res.ok) { throw new Error("lens_fetch_failed"); }
        return res.json();
      })
      .then(function (payload) {
        lensRoots().forEach(function (root) {
          renderProvision(root, payload);
        });
        if (!shouldKeepPolling(payload)) {
          if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        }
      })
      .catch(function () {
        /* silent — operator can retry via row re-select */
      })
      .finally(function () {
        pollInFlight = false;
      });
  }

  function startLensPolling(detail) {
    clearPoll();
    activeLensUrl = (detail && detail.lensApiUrl) || "";
    activeRequeueUrl = (detail && detail.requeueApiUrl) || "";
    if (!activeLensUrl) { return; }
    fetchLens();
    pollTimer = setInterval(fetchLens, POLL_MS);
  }

  function postRequeue(btn) {
    if (!activeRequeueUrl || !btn) { return; }
    btn.disabled = true;
    fetch(activeRequeueUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: "{}",
    })
      .then(function (res) {
        return res.json().then(function (body) {
          return { ok: res.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          throw new Error((result.body && result.body.error) || "requeue_failed");
        }
        var payload = result.body.lens || result.body;
        lensRoots().forEach(function (root) {
          renderProvision(root, payload);
        });
        if (!pollTimer && activeLensUrl) {
          pollTimer = setInterval(fetchLens, POLL_MS);
        }
        fetchLens();
      })
      .catch(function (err) {
        var roots = lensRoots();
        roots.forEach(function (root) {
          var errEl = root.querySelector("[data-rmc-copilot-lens-provision-error]");
          if (errEl) {
            errEl.textContent = String(err.message || "Requeue failed");
            errEl.hidden = false;
          }
        });
      })
      .finally(function () {
        if (btn) { btn.disabled = false; }
      });
  }

  document.addEventListener("rmc:row-detail-open", function (ev) {
    startLensPolling(ev.detail || {});
  });

  document.addEventListener("rmc:row-detail-close", clearPoll);

  document.addEventListener("click", function (ev) {
    var btn = ev.target && ev.target.closest("[data-rmc-copilot-lens-requeue]");
    if (!btn) { return; }
    ev.preventDefault();
    postRequeue(btn);
  });
})();
