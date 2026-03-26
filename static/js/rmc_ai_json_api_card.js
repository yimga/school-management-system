/**
 * POST arbitrary JSON to /api/ai/* endpoints (data-rmc-ai-json-api).
 * Expects valid JSON in textarea; CSRF from cookie. Does not inject secrets.
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
    if (card.getAttribute("data-rmc-json-bound") === "1") return;
    card.setAttribute("data-rmc-json-bound", "1");
    var url = card.getAttribute("data-ai-url");
    var ta = card.querySelector("[data-rmc-ai-json-body]");
    var btn = card.querySelector("[data-rmc-ai-json-run]");
    var out = card.querySelector("[data-rmc-ai-json-out]");
    if (!url || !btn) return;
    btn.addEventListener("click", function () {
      var raw = (ta && ta.value) ? ta.value.trim() : "{}";
      var body;
      try {
        body = JSON.parse(raw);
      } catch (e) {
        if (out) out.textContent = "Invalid JSON: " + e;
        return;
      }
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
        body: JSON.stringify(body),
      })
        .then(function (r) {
          return r.text().then(function (t) {
            return { ok: r.ok, status: r.status, text: t };
          });
        })
        .then(function (res) {
          btn.disabled = false;
          if (!out) return;
          try {
            out.textContent = JSON.stringify(JSON.parse(res.text), null, 2);
          } catch (e) {
            out.textContent = res.text || String(res.status);
          }
        })
        .catch(function (err) {
          btn.disabled = false;
          if (out) out.textContent = String(err);
        });
    });
  }

  function scan() {
    document.querySelectorAll("[data-rmc-ai-json-api]").forEach(bindCard);
  }

  window.addEventListener("load", scan);
})();
