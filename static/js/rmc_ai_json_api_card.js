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
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
      return meta.content;
    }
    return getCookie("csrftoken") || getCookie("rmc_manager_csrftoken") || "";
  }

  function formatPayload(data, status) {
    if (!data || typeof data !== "object") {
      return String(data || status);
    }
    if (data.success && data.guided) {
      var g = data.guided;
      var meta = data.meta || {};
      var lines = [];
      if (meta.degraded) {
        lines.push("Degraded mode (rules / structured fallback).");
      }
      lines.push(g.summary || "");
      (g.actions || []).forEach(function (a) {
        lines.push("- " + (a.title || "") + ": " + (a.detail || ""));
      });
      (g.cautions || []).forEach(function (c) {
        lines.push("! " + c);
      });
      if (!lines.join("").trim()) {
        lines.push("(empty guided response)");
      }
      return lines.join("\n");
    }
    if (!data.success) {
      return data.error || data.detail || JSON.stringify(data, null, 2);
    }
    return JSON.stringify(data, null, 2);
  }

  function bindCard(card) {
    if (card.getAttribute("data-rmc-json-bound") === "1") return;
    card.setAttribute("data-rmc-json-bound", "1");
    var ta = card.querySelector("[data-rmc-ai-json-body]");
    var btn = card.querySelector("[data-rmc-ai-json-run]");
    var out = card.querySelector("[data-rmc-ai-json-out]");
    if (!btn) return;
    var originalBtnHTML = btn.innerHTML;
    function setBusy(busy) {
      if (busy) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        btn.innerHTML =
          '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Running…';
      } else {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
        btn.innerHTML = originalBtnHTML;
      }
    }
    btn.addEventListener("click", function () {
      var url = card.getAttribute("data-ai-url");
      if (!url) {
        if (out) out.textContent = "AI endpoint not configured for this card.";
        return;
      }
      var raw = ta && ta.value ? ta.value.trim() : "{}";
      var body;
      try {
        body = JSON.parse(raw);
      } catch (e) {
        if (out) out.textContent = "Invalid JSON: " + e;
        return;
      }
      setBusy(true);
      if (out) out.textContent = "Running…";
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
          var ct = (r.headers.get("content-type") || "").toLowerCase();
          if (ct.indexOf("application/json") < 0) {
            return r.text().then(function (t) {
              return { ok: false, status: r.status, data: { error: t || "non-json" } };
            });
          }
          return r.json().then(function (data) {
            return { ok: r.ok, status: r.status, data: data };
          });
        })
        .then(function (res) {
          setBusy(false);
          if (!out) return;
          if (res.status === 401 || res.status === 403) {
            out.textContent = "Session expired or permission denied. Refresh and sign in.";
            return;
          }
          out.textContent = formatPayload(res.data, res.status);
        })
        .catch(function () {
          setBusy(false);
          if (out) out.textContent = "Network error. Check connection and retry.";
        });
    });
  }

  function scan() {
    document.querySelectorAll("[data-rmc-ai-json-api]").forEach(bindCard);
  }

  function runAllGatewayCards() {
    var cards = document.querySelectorAll(
      "#ai-gw-accordion [data-rmc-ai-json-api] [data-rmc-ai-json-run]"
    );
    var idx = 0;
    function next() {
      if (idx >= cards.length) return;
      cards[idx].click();
      idx += 1;
      if (idx < cards.length) {
        window.setTimeout(next, 400);
      }
    }
    next();
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-rmc-ai-gateway-test-all]");
    if (!btn) return;
    runAllGatewayCards();
  });

  window.addEventListener("load", scan);
})();
