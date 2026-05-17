/* v2.94 — Integrations hub: synthetic webhook "Test" button.
 *
 * CSP-friendly: no inline handlers, no inline styles. The button declares
 * its target URL via `data-rmc-test-webhook` and we POST in-place with the
 * CSRF token. Result renders as a transient banner inside the same row.
 *
 * Defensive: if fetch fails, we surface the raw error so the operator
 * doesn't see a silent dead click.
 */
(function () {
  "use strict";

  function getCookie(name) {
    var v = "; " + document.cookie;
    var parts = v.split("; " + name + "=");
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }

  function renderResult(button, result, isError) {
    var existing = button.parentElement.querySelector(".rmc-test-webhook-result");
    if (existing) existing.remove();
    var box = document.createElement("div");
    box.className = "small mt-1 rmc-test-webhook-result " +
      (isError ? "text-danger" : (result && result.ok ? "text-success" : "text-warning"));
    if (isError) {
      box.textContent = "Test failed: " + String(result);
    } else if (result && result.ok) {
      box.textContent =
        "Verified ✓ · handler returned " +
        (result.handler_status || "n/a") +
        (result.handler_present ? "" : " · no handler registered for this slug");
    } else {
      box.textContent =
        "Verify failed: " + (result && result.verify_reason || "unknown");
    }
    button.parentElement.appendChild(box);
    setTimeout(function () { try { box.remove(); } catch (_) {} }, 8000);
  }

  function bind(button) {
    if (button.dataset.rmcBound === "1") return;
    button.dataset.rmcBound = "1";
    button.addEventListener("click", function () {
      var url = button.getAttribute("data-rmc-test-webhook");
      if (!url) return;
      button.disabled = true;
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": getCookie("csrftoken"),
          "Accept": "application/json",
        },
      })
        .then(function (r) { return r.json().catch(function () { return { ok: false, error: "non_json_response", status: r.status }; }); })
        .then(function (j) { renderResult(button, j, false); })
        .catch(function (err) { renderResult(button, err && err.message || err, true); })
        .then(function () { button.disabled = false; });
    });
  }

  function init() {
    var buttons = document.querySelectorAll("[data-rmc-test-webhook]");
    for (var i = 0; i < buttons.length; i++) bind(buttons[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
