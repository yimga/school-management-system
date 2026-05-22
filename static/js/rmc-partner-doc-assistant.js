/**
 * Partner documentation assistant — wraps api:ai-interop-assistant (batch 1395).
 */
(function () {
  "use strict";

  function csrfToken() {
    const el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function apiUrl() {
    const el = document.getElementById("page-data-partner-doc-1");
    if (!el) return "";
    try {
      const data = JSON.parse(el.textContent || "{}");
      return data.interop_api_url || "";
    } catch (e) {
      return "";
    }
  }

  document.querySelectorAll("[data-rmc-partner-doc-assistant]").forEach(function (root) {
    const url = apiUrl();
    const queryEl = root.querySelector("[data-rmc-partner-query]");
    const statusEl = root.querySelector("[data-rmc-partner-status]");
    const outEl = root.querySelector("[data-rmc-partner-out]");
    const btn = root.querySelector("[data-rmc-partner-submit]");
    if (!url || !queryEl || !btn) return;

    btn.addEventListener("click", function () {
      const q = (queryEl.value || "").trim();
      if (!q) {
        if (statusEl) statusEl.textContent = "Enter a question.";
        return;
      }
      if (statusEl) statusEl.textContent = "…";
      if (outEl) {
        outEl.hidden = true;
        outEl.textContent = "";
      }
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ query: q }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (statusEl) statusEl.textContent = "";
          const guided = data.guided || {};
          const text = guided.summary || data.error || "";
          if (outEl) {
            outEl.hidden = !text;
            outEl.textContent = text;
          }
        })
        .catch(function () {
          if (statusEl) statusEl.textContent = "Request failed";
        });
    });
  });
})();
