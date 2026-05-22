/**
 * Workflow playbook assistant (onboarding / offboarding) — batch 1394.
 */
(function () {
  "use strict";

  function csrfToken() {
    const el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function init(root) {
    const url = root.getAttribute("data-playbook-url");
    const form = root.querySelector("[data-rmc-playbook-form]");
    const queryEl = root.querySelector("[data-rmc-playbook-query]");
    const statusEl = root.querySelector("[data-rmc-playbook-status]");
    const answerEl = root.querySelector("[data-rmc-playbook-answer]");
    const submitBtn = root.querySelector("[data-rmc-playbook-submit]");
    if (!url || !queryEl || !submitBtn) return;

    function setStatus(msg) {
      if (statusEl) statusEl.textContent = msg || "";
    }

    submitBtn.addEventListener("click", function () {
      const q = (queryEl.value || "").trim();
      if (!q) {
        setStatus("Enter a question.");
        return;
      }
      setStatus("…");
      if (answerEl) {
        answerEl.hidden = true;
        answerEl.textContent = "";
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
          return r.json().then(function (data) {
            return { ok: r.ok, data: data };
          });
        })
        .then(function (res) {
          setStatus("");
          if (!res.ok || !res.data || res.data.success === false) {
            setStatus((res.data && res.data.error) || "Unavailable");
            return;
          }
          const guided = res.data.guided || res.data.response || {};
          const summary =
            (typeof guided === "object" && guided.summary) ||
            (typeof res.data.response === "string" ? res.data.response : "") ||
            "";
          if (answerEl) {
            answerEl.hidden = !summary;
            answerEl.textContent = summary;
          }
        })
        .catch(function () {
          setStatus("Request failed");
        });
    });
  }

  document.querySelectorAll("[data-rmc-workflow-playbook]").forEach(init);
})();
