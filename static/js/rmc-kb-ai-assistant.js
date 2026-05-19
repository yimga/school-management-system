/**
 * KB / Help Center AI panel — engine-room support assistant with escalation.
 */
(function () {
  "use strict";

  var MAX_QUERY_CHARS = 8000;

  function readConfig(panel) {
    return {
      apiUrl:
        panel.getAttribute("data-support-assistant-url") ||
        document.body.getAttribute("data-support-assistant-url") ||
        document.body.getAttribute("data-ai-copilot-url") ||
        "",
      escalateUrl: panel.getAttribute("data-escalate-url") || "",
      slug: panel.getAttribute("data-kb-article-slug") || "",
      title: panel.getAttribute("data-kb-article-title") || "",
    };
  }

  function buildPrompt(userText, cfg) {
    var prefix =
      "You are the RunMyCampus help assistant. Answer using knowledge base and platform documentation. ";
    if (cfg.title) {
      prefix += 'Current article: "' + cfg.title + '". ';
    }
    if (cfg.slug) {
      prefix += "Article slug: " + cfg.slug + ". ";
    }
    return prefix + "Question: " + userText;
  }

  function truncateQuery(text) {
    var t = (text || "").trim();
    if (t.length <= MAX_QUERY_CHARS) {
      return t;
    }
    return t.slice(0, MAX_QUERY_CHARS);
  }

  function getCsrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }

  function activeUrl() {
    return window.location.pathname || "/";
  }

  function streamText(el, text, onDone) {
    var full = text || "";
    if (!full) {
      el.textContent = "";
      if (onDone) onDone();
      return;
    }
    var i = 0;
    var chunk = Math.max(8, Math.floor(full.length / 40));
    el.textContent = "";
    function tick() {
      i = Math.min(full.length, i + chunk);
      el.textContent = full.slice(0, i);
      if (i < full.length) {
        window.requestAnimationFrame(tick);
      } else if (onDone) {
        onDone();
      }
    }
    tick();
  }

  function showFallback(panel, show) {
    var fb = panel.querySelector("[data-rmc-kb-ai-fallback]");
    if (fb) {
      fb.classList.toggle("d-none", !show);
    }
  }

  function showEscalate(panel, cfg, query, show) {
    var link = panel.querySelector("[data-rmc-kb-ai-escalate]");
    if (!link || !cfg.escalateUrl) {
      return;
    }
    if (show) {
      var params = new URLSearchParams();
      params.set("category", "SUPPORT");
      if (query) {
        params.set("subject", "AI help escalation");
        params.set("message", query.slice(0, 1500));
      }
      link.href = cfg.escalateUrl + "?" + params.toString();
      link.classList.remove("d-none");
    } else {
      link.classList.add("d-none");
    }
  }

  document.querySelectorAll("[data-rmc-kb-ai-panel]").forEach(function (panel) {
    var askBtn = panel.querySelector("[data-rmc-kb-ai-ask]");
    var input = panel.querySelector("#rmc-kb-ai-prompt");
    var answerEl = panel.querySelector("[data-rmc-kb-ai-answer]");
    if (!askBtn || !input || !answerEl) {
      return;
    }

    askBtn.addEventListener("click", function () {
      var cfg = readConfig(panel);
      var text = truncateQuery(input.value);
      if (!text) {
        return;
      }
      if (!cfg.apiUrl) {
        answerEl.classList.remove("d-none");
        answerEl.textContent = "Support assistant endpoint is not configured on this host.";
        showFallback(panel, true);
        showEscalate(panel, cfg, text, true);
        return;
      }

      askBtn.disabled = true;
      showFallback(panel, false);
      showEscalate(panel, cfg, text, false);
      answerEl.classList.remove("d-none");
      answerEl.textContent = "Thinking…";

      fetch(cfg.apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrf(),
        },
        credentials: "same-origin",
        body: JSON.stringify({
          query: buildPrompt(text, cfg),
          active_url: activeUrl(),
          history: "",
        }),
      })
        .then(function (r) {
          return r.json().then(function (body) {
            return { ok: r.ok, status: r.status, body: body };
          });
        })
        .then(function (res) {
          if (!res.ok) {
            var err =
              (res.body && (res.body.error || res.body.detail)) ||
              "Could not reach the support assistant.";
            answerEl.textContent = err;
            showFallback(panel, true);
            showEscalate(panel, cfg, text, true);
            return;
          }
          var reply =
            (res.body && (res.body.response || res.body.reply || res.body.message)) ||
            "No answer returned.";
          var escalate = Boolean(res.body && res.body.escalation_required);
          streamText(answerEl, reply, function () {
            if (escalate) {
              showEscalate(panel, cfg, text, true);
            }
          });
        })
        .catch(function () {
          answerEl.textContent =
            "Network error. Use the article below or escalate to a human agent.";
          showFallback(panel, true);
          showEscalate(panel, cfg, text, true);
        })
        .finally(function () {
          askBtn.disabled = false;
        });
    });
  });
})();
