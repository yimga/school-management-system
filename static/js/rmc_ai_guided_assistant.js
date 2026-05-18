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
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
      return meta.content;
    }
    return getCookie("csrftoken") || getCookie("rmc_manager_csrftoken") || "";
  }

  function friendlyError(data, status) {
    if (status === 403 && data && data.error === "auth") {
      return "Request blocked (CSRF or session). Refresh the page and try again.";
    }
    if (status === 401 || status === 403) {
      return "Session expired or permission denied. Refresh the page and sign in again.";
    }
    if (!data || typeof data !== "object") {
      return "Unexpected response from the AI gateway.";
    }
    var err = data.error || data.detail || "";
    if (err === "unavailable" || status === 503) {
      return "AI service is temporarily unavailable. Try again shortly or check provider health.";
    }
    if (err === "Rate limit exceeded. Try again later." || status === 429) {
      return err;
    }
    if (String(err).toLowerCase().indexOf("safety policy") >= 0) {
      return "That prompt was blocked by the safety policy. Rephrase without override instructions.";
    }
    if (data.budget_exceeded || String(err).toLowerCase().indexOf("budget") >= 0) {
      return "Daily AI budget exceeded for this tenant.";
    }
    if (err) {
      return String(err);
    }
    return "Request failed (" + status + ").";
  }

  function parseResponse(r) {
    var ct = (r.headers.get("content-type") || "").toLowerCase();
    if (ct.indexOf("application/json") < 0) {
      if (r.status === 401 || r.status === 403) {
        return Promise.resolve({
          ok: false,
          status: r.status,
          data: { error: "auth" },
        });
      }
      return Promise.resolve({
        ok: false,
        status: r.status,
        data: { error: "non_json" },
      });
    }
    return r.json().then(function (data) {
      return { ok: r.ok, status: r.status, data: data };
    });
  }

  function renderGuided(out, g, meta, cites) {
    var lines = [];
    if (meta && meta.degraded) {
      lines.push("Degraded mode: using retrieved docs and platform hints (live model not used).");
    }
    if (meta && meta.schema_validation_failed) {
      lines.push(
        "Model output did not match the expected format; showing a safe structured fallback."
      );
    }
    if (cites && cites.length) {
      lines.push(
        "(Grounded with " + cites.length + " retrieved memory snippet(s).)"
      );
    }
    lines.push(g.summary || "");
    (g.actions || []).forEach(function (a) {
      lines.push("- " + (a.title || "") + ": " + (a.detail || ""));
    });
    (g.cautions || []).forEach(function (c) {
      lines.push("! " + c);
    });
    (g.references || []).forEach(function (ref) {
      lines.push("ref: " + ref);
    });
  if (!lines.join("").trim()) {
      lines.push("No answer text returned. Try a more specific question or connect Ollama.");
    }
    out.textContent = lines.join("\n");
    out.hidden = false;
    out.classList.remove("d-none");
  }

  function bindCard(card) {
    if (card.getAttribute("data-rmc-ai-bound") === "1") return;
    card.setAttribute("data-rmc-ai-bound", "1");
    var out = card.querySelector("[data-rmc-ai-out]");
    var ta = card.querySelector("[data-rmc-ai-query]");
    var btn = card.querySelector("[data-rmc-ai-run]");
    if (!btn) return;
    function _showOut(content) {
      if (!out) return;
      out.textContent = content;
      out.hidden = false;
      out.classList.remove("d-none");
    }
    var originalBtnHTML = btn.innerHTML;
    function _setBusy(busy) {
      if (busy) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        btn.innerHTML =
          '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Thinking…';
      } else {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
        btn.innerHTML = originalBtnHTML;
      }
    }
    btn.addEventListener("click", function () {
      var url = card.getAttribute("data-ai-url");
      if (!url) {
        _showOut(
          "Pick an assistant on the left first, then ask your question."
        );
        return;
      }
      var q = ta && ta.value ? ta.value.trim() : "";
      if (!q) {
        _showOut("Enter a question.");
        if (ta) ta.focus();
        return;
      }
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        _showOut(
          "You appear to be offline. AI assistants need a connection to the school server. " +
            "When offline mode is enabled, attendance and grades can still be captured locally and sync later."
        );
        return;
      }
      var payload = { query: q };
      var mode = card.getAttribute("data-studio-mode");
      if (mode) payload.studio_mode = mode;
      _setBusy(true);
      _showOut("Thinking…");
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
        .then(parseResponse)
        .then(function (res) {
          _setBusy(false);
          if (!out) return;
          if (!res.ok || !res.data || !res.data.success) {
            _showOut(friendlyError(res.data, res.status));
            return;
          }
          var g = res.data.guided || {};
          var meta = res.data.meta || {};
          var cites = res.data.citations;
          renderGuided(out, g, meta, cites);
          if (card.closest("[data-rmc-ai-center]")) {
            document.dispatchEvent(
              new CustomEvent("rmc:ai-guided-answered", {
                detail: {
                  question: q,
                  answer: String(g.summary || "").slice(0, 500),
                },
              })
            );
          }
        })
        .catch(function () {
          _setBusy(false);
          _showOut("Network error. Check your connection and try again.");
        });
    });
    if (ta) {
      ta.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
          ev.preventDefault();
          btn.click();
        }
      });
    }
  }

  function scan() {
    document.querySelectorAll("[data-rmc-ai-guided]").forEach(bindCard);
  }

  window.addEventListener("load", scan);
  document.addEventListener("rmc:ai-guided-rebind", scan);
})();
