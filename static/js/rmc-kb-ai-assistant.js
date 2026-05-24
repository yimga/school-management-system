/**

 * KB / Help Center AI panel — SSE support assistant with JSON fallback.

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

      streamUrl:

        panel.getAttribute("data-support-assistant-stream-url") ||

        document.body.getAttribute("data-support-assistant-stream-url") ||

        "",

      escalateUrl: panel.getAttribute("data-escalate-url") || "",

      ratingUrl: panel.getAttribute("data-support-session-rating-url") || "",

      slug: panel.getAttribute("data-kb-article-slug") || "",

      title: panel.getAttribute("data-kb-article-title") || "",

    };

  }



  function csrfToken() {

    var input = document.querySelector("[name=csrfmiddlewaretoken]");

    return input ? input.value : "";

  }



  function postSessionRating(cfg, text, thumbs) {

    if (!cfg.ratingUrl) return;

    fetch(cfg.ratingUrl, {

      method: "POST",

      credentials: "same-origin",

      headers: {

        "Content-Type": "application/json",

        "X-CSRFToken": csrfToken(),

      },

      body: JSON.stringify({

        thumbs: thumbs,

        query: text,

        task_type: "support_assistant",

        active_url: window.location.pathname || "",

      }),

    }).catch(function () {});

  }



  function showCsat(panel) {

    var csat = panel.querySelector("[data-rmc-kb-ai-csat]");

    if (csat) csat.classList.remove("d-none");

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
    try {
      var params = new URLSearchParams(window.location.search || "");
      var override = (params.get("active_url") || "").trim();
      if (override) {
        return override;
      }
      var root = document.querySelector("[data-rmc-page='help-center']");
      if (root) {
        var attr = (root.getAttribute("data-rmc-help-active-url") || "").trim();
        if (attr) {
          return attr;
        }
      }
    } catch (_e) {}
    return window.location.pathname || "/";
  }



  function showFallback(panel, show) {

    var fb = panel.querySelector("[data-rmc-kb-ai-fallback]");

    if (fb) {

      fb.classList.toggle("d-none", !show);

    }

  }



  function showOffline(panel, show) {

    var el = panel.querySelector("[data-rmc-kb-ai-offline]");

    if (el) {

      el.classList.toggle("d-none", !show);

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



  function parseSseChunk(buffer, onEvent) {

    var parts = buffer.split("\n\n");

    var rest = parts.pop() || "";

    parts.forEach(function (block) {

      var lines = block.split("\n");

      var eventName = "message";

      var dataLines = [];

      lines.forEach(function (line) {

        if (line.indexOf("event:") === 0) {

          eventName = line.slice(6).trim();

        } else if (line.indexOf("data:") === 0) {

          dataLines.push(line.slice(5).trim());

        }

      });

      if (!dataLines.length) {

        return;

      }

      try {

        onEvent(eventName, JSON.parse(dataLines.join("\n")));

      } catch (e) {

        /* ignore malformed frame */

      }

    });

    return rest;

  }



  function consumeSseStream(response, handlers) {

    if (!response.body || !window.TextDecoder) {

      return Promise.reject(new Error("streaming unsupported"));

    }

    var reader = response.body.getReader();

    var decoder = new TextDecoder("utf-8");

    var buffer = "";

    function pump() {

      return reader.read().then(function (result) {

        if (result.done) {

          return;

        }

        buffer += decoder.decode(result.value, { stream: true });

        buffer = parseSseChunk(buffer, handlers.onEvent);

        return pump();

      });

    }

    return pump();

  }



  function askViaJson(cfg, text, panel, answerEl) {

    return fetch(cfg.apiUrl, {

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

          return { ok: r.ok, body: body };

        });

      })

      .then(function (res) {

        if (!res.ok) {

          if (res.body && res.body.offline_mode) {

            showOffline(panel, true);

            showFallback(panel, false);

          }

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

        answerEl.textContent = reply;

        showCsat(panel);

        if (res.body && res.body.escalation_required) {

          showEscalate(panel, cfg, text, true);

        }

      });

  }



  function askViaSse(cfg, text, panel, answerEl) {

    return fetch(cfg.streamUrl, {

      method: "POST",

      headers: {

        "Content-Type": "application/json",

        Accept: "text/event-stream",

        "X-CSRFToken": getCsrf(),

      },

      credentials: "same-origin",

      body: JSON.stringify({

        query: buildPrompt(text, cfg),

        active_url: activeUrl(),

        history: "",

      }),

    }).then(function (response) {

      if (!response.ok) {

        return askViaJson(cfg, text, panel, answerEl);

      }

      var full = "";

      return consumeSseStream(response, {

        onEvent: function (eventName, payload) {

          if (eventName === "delta" && payload && payload.text) {

            full += payload.text;

            answerEl.textContent = full;

          }

          if (eventName === "done" && payload) {

            if (payload.response) {

              answerEl.textContent = payload.response;

            }

            showCsat(panel);

            if (payload.escalation_required) {

              showEscalate(panel, cfg, text, true);

            }

          }

          if (eventName === "error") {

            var err = (payload && payload.error) || "Stream failed.";

            answerEl.textContent = err;

            showFallback(panel, true);

            showEscalate(panel, cfg, text, true);

          }

        },

      }).catch(function () {

        return askViaJson(cfg, text, panel, answerEl);

      });

    });

  }



  document.querySelectorAll("[data-rmc-kb-ai-panel]").forEach(function (panel) {

    var cfg0 = readConfig(panel);

    var upBtn = panel.querySelector("[data-rmc-kb-ai-csat-up]");

    var downBtn = panel.querySelector("[data-rmc-kb-ai-csat-down]");

    var lastQuery = "";

    if (upBtn) {

      upBtn.addEventListener("click", function () {

        postSessionRating(cfg0, lastQuery, "up");

        panel.querySelector("[data-rmc-kb-ai-csat]").classList.add("d-none");

      });

    }

    if (downBtn) {

      downBtn.addEventListener("click", function () {

        postSessionRating(cfg0, lastQuery, "down");

        panel.querySelector("[data-rmc-kb-ai-csat]").classList.add("d-none");

      });

    }



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

      lastQuery = text;

      var csatEl = panel.querySelector("[data-rmc-kb-ai-csat]");

      if (csatEl) csatEl.classList.add("d-none");

      if (!cfg.apiUrl && !cfg.streamUrl) {

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



      var chain = cfg.streamUrl

        ? askViaSse(cfg, text, panel, answerEl)

        : askViaJson(cfg, text, panel, answerEl);



      chain

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


