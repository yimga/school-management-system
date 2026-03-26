/**
 * Binds POST /api/ai/* guided assistant cards (data-rmc-ai-guided).
 * CSRF from cookie; never sends secrets from inputs (operator pastes only non-secret snapshots).
 */
(function () {
  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      var cookies = document.cookie.split(";");
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function getCsrf() {
    return getCookie("csrftoken") || getCookie("rmc_manager_csrftoken") || "";
  }

  function bindCard(card) {
    if (card.getAttribute("data-rmc-ai-bound") === "1") return;
    card.setAttribute("data-rmc-ai-bound", "1");
    var url = card.getAttribute("data-ai-url");
    var out = card.querySelector("[data-rmc-ai-out]");
    var ta = card.querySelector("[data-rmc-ai-query]");
    var btn = card.querySelector("[data-rmc-ai-run]");
    if (!url || !btn) return;
    btn.addEventListener("click", function () {
      var q = (ta && ta.value) ? ta.value.trim() : "";
      if (!q) {
        if (out) out.textContent = "Enter a question.";
        return;
      }
      var payload = { query: q };
      var mode = card.getAttribute("data-studio-mode");
      if (mode) payload.studio_mode = mode;
      btn.disabled = true;
      if (out) out.textContent = "…";
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrf(),
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      })
        .then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, data: data };
          });
        })
        .then(function (res) {
          btn.disabled = false;
          if (!out) return;
          if (!res.ok || !res.data.success) {
            out.textContent = JSON.stringify(res.data, null, 2);
            return;
          }
          var g = res.data.guided || {};
          var lines = [];
          lines.push(g.summary || "");
          (g.actions || []).forEach(function (a) {
            lines.push("- " + (a.title || "") + ": " + (a.detail || ""));
          });
          (g.cautions || []).forEach(function (c) {
            lines.push("! " + c);
          });
          (g.references || []).forEach(function (r) {
            lines.push("ref: " + r);
          });
          out.textContent = lines.join("\n");
        })
        .catch(function (err) {
          btn.disabled = false;
          if (out) out.textContent = String(err);
        });
    });
  }

  function scan() {
    document.querySelectorAll("[data-rmc-ai-guided]").forEach(bindCard);
  }

  /* After all deferred partials/cards are in the DOM */
  window.addEventListener("load", scan);
})();
