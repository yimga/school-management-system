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

  function activePageUrl(card) {
    if (card) {
      var override = card.getAttribute("data-active-url-override");
      if (override) return override;
    }
    if (typeof window === "undefined" || !window.location) return "";
    return (window.location.pathname || "") + (window.location.search || "");
  }

  function renderEngineRoom(out, data, card) {
    var lines = [];
    var text = String(data.response || "").trim();
    if (text) lines.push(text);
    if (data.meta && data.meta.degraded) {
      lines.unshift("Degraded mode: using retrieved docs (live model not used).");
    }
    if (!lines.join("").trim()) {
      lines.push("No answer text returned.");
    }
    out.textContent = lines.join("\n\n");
    out.hidden = false;
    out.classList.remove("d-none");

    var escBar = card.querySelector("[data-rmc-ai-escalation]");
    var helpUrl = card.getAttribute("data-helpdesk-url") || "";
    if (escBar) {
      if (data.escalation_required && helpUrl) {
        escBar.hidden = false;
        escBar.classList.remove("d-none");
        var link = escBar.querySelector("[data-rmc-ai-escalate-link]");
        if (link) link.setAttribute("href", helpUrl);
      } else {
        escBar.hidden = true;
        escBar.classList.add("d-none");
      }
    }

    var fb = card.querySelector("[data-rmc-ai-feedback]");
    if (fb) {
      fb.hidden = false;
      fb.classList.remove("d-none");
      fb.setAttribute("data-rmc-ai-feedback-tier", (data.meta && data.meta.tier) || "rules");
      fb.setAttribute("data-rmc-ai-feedback-task", "support_suggest");
    }
  }

  function renderGuided(out, g, meta, cites) {
    var lines = [];
    if (meta && meta.live_ai_unavailable) {
      lines.push("Live AI is unavailable on this server. The answer below is not from a language model.");
    } else if (meta && meta.degraded) {
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
      var payload = { query: q, active_url: activePageUrl(card) };
      var mode = card.getAttribute("data-studio-mode");
      if (mode) payload.studio_mode = mode;
      var apiKind = card.getAttribute("data-api-kind") || "";
      if (apiKind === "import_resolver") {
        try {
          var parsed = JSON.parse(q);
          if (Array.isArray(parsed)) {
            payload = { errors: parsed, import_kind: "csv" };
          } else if (parsed && Array.isArray(parsed.errors)) {
            payload = {
              errors: parsed.errors,
              import_kind: parsed.import_kind || "csv",
            };
          }
        } catch (e) {
          payload = {
            errors: [{ row: 1, message: q }],
            import_kind: "csv",
          };
        }
      } else if (apiKind === "guided_tour") {
        payload = { goal: q, active_url: activePageUrl(card) };
      } else if (apiKind === "report_generator") {
        payload = { query: q };
      }

      _setBusy(true);
      _showOut("Thinking…");
      var escBar = card.querySelector("[data-rmc-ai-escalation]");
      if (escBar) {
        escBar.hidden = true;
        escBar.classList.add("d-none");
      }
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
          if (!res.ok || !res.data || res.data.success === false) {
            if (res.data && res.data.guided && res.data.error === "live_ai_unavailable") {
              renderGuided(out, res.data.guided, res.data.meta || {}, res.data.citations);
              return;
            }
            _showOut(friendlyError(res.data, res.status));
            return;
          }
          if (res.data.response !== undefined && res.data.response !== null) {
            renderEngineRoom(out, res.data, card);
            if (card.closest("[data-rmc-ai-center]")) {
              document.dispatchEvent(
                new CustomEvent("rmc:ai-guided-answered", {
                  detail: {
                    question: q,
                    answer: String(res.data.response || "").slice(0, 500),
                  },
                })
              );
            }
            return;
          }
          var g = res.data.guided || {};
          var meta = res.data.meta || {};
          var cites = res.data.citations;
          if (res.data.recommendations && res.data.recommendations.length) {
            g = {
              summary: g.summary || "Report recommendations",
              actions: res.data.recommendations.map(function (r) {
                return {
                  title: r.name || "Report",
                  detail: (r.description || "") + (r.fit ? " — " + r.fit : ""),
                };
              }),
              cautions: g.cautions || [],
              references: g.references || [],
            };
          }
          if (res.data.steps && res.data.steps.length) {
            g = {
              summary: g.summary || res.data.narrative || "Guided tour",
              actions: res.data.steps.map(function (s, i) {
                return {
                  title: (i + 1) + ". " + (s.title || "Step"),
                  detail:
                    (s.execution_path || "") +
                    (s.url ? " → " + s.url : "") +
                    " " +
                    (s.action || ""),
                };
              }),
              cautions: g.cautions || [],
              references: g.references || [],
            };
          }
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

  function bindFeedback(card) {
    var fb = card.querySelector("[data-rmc-ai-feedback]");
    if (!fb || fb.getAttribute("data-rmc-ai-feedback-bound") === "1") return;
    fb.setAttribute("data-rmc-ai-feedback-bound", "1");
    var feedbackUrl = card.getAttribute("data-feedback-url");
    if (!feedbackUrl) return;
    fb.querySelectorAll("[data-rmc-ai-feedback-vote]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var accepted = btn.getAttribute("data-vote") === "up";
        fetch(feedbackUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrf(),
            Accept: "application/json",
          },
          body: JSON.stringify({
            task_type: fb.getAttribute("data-rmc-ai-feedback-task") || "support_suggest",
            tier: fb.getAttribute("data-rmc-ai-feedback-tier") || "rules",
            accepted: accepted,
            feature: "engine_room",
          }),
        }).catch(function () {});
        fb.querySelectorAll("[data-rmc-ai-feedback-vote]").forEach(function (b) {
          b.disabled = true;
        });
      });
    });
  }

  function scan() {
    document.querySelectorAll("[data-rmc-ai-guided]").forEach(function (card) {
      bindCard(card);
      bindFeedback(card);
    });
  }

  window.addEventListener("load", scan);
  document.addEventListener("rmc:ai-guided-rebind", scan);
})();
