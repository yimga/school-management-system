/*
 * rmc-thread-ai.js — in-thread AI assist (IM-8).
 *
 * Two opt-in controls, both POST JSON and are CSRF-safe (token read from the
 * page's form field / meta, never the HttpOnly cookie):
 *
 *   Improve draft — [data-rmc-ai-improve] button with data-endpoint + data-target
 *     (a textarea id). Sends {text: <textarea>} and replaces the textarea with the
 *     returned `draft` (clearer plain-language rewrite). The user always reviews.
 *
 *   Summarize thread — [data-rmc-ai-summarize] button with data-endpoint +
 *     data-scope ("direct"|"group") + data-id + data-panel (a selector). Sends
 *     {scope, id} and writes the returned `summary` into the panel via textContent.
 *
 * Everything fails soft: a disabled/unavailable AI just shows a status message;
 * messaging never depends on it.
 */
(function () {
  "use strict";

  if (window.__rmcThreadAiInit) {
    return;
  }
  window.__rmcThreadAiInit = true;

  function csrfToken() {
    var field = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (field && field.value) {
      return field.value;
    }
    var meta = document.querySelector("meta[name=csrf-token]");
    return meta ? meta.getAttribute("content") : "";
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(body || {}),
    }).then(function (resp) {
      return resp.json().then(function (data) {
        if (!resp.ok) {
          throw (data && data.error) || "Service unavailable.";
        }
        return data;
      });
    });
  }

  function wireImprove(btn) {
    var endpoint = btn.getAttribute("data-endpoint");
    var textarea = document.getElementById(btn.getAttribute("data-target") || "");
    var status = btn.parentNode
      ? btn.parentNode.querySelector("[data-rmc-ai-status]")
      : null;
    if (!endpoint || !textarea) {
      return;
    }
    btn.addEventListener("click", function () {
      var text = (textarea.value || "").trim();
      if (!text) {
        if (status) status.textContent = "Type a message first.";
        return;
      }
      btn.disabled = true;
      if (status) status.textContent = "Improving…";
      postJson(endpoint, { text: text })
        .then(function (data) {
          var out = data && (data.improved || data.draft);
          if (out) {
            textarea.value = out;
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
            if (status) status.textContent = "Updated — please review.";
          } else if (status) {
            status.textContent = "No suggestion.";
          }
        })
        .catch(function (err) {
          if (status) {
            status.textContent = typeof err === "string" ? err : "Unavailable.";
          }
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  }

  function wireSummarize(btn) {
    var endpoint = btn.getAttribute("data-endpoint");
    var panel = document.querySelector(btn.getAttribute("data-panel") || "");
    if (!endpoint || !panel) {
      return;
    }
    btn.addEventListener("click", function () {
      btn.disabled = true;
      panel.hidden = false;
      panel.textContent = "Summarizing…";
      postJson(endpoint, {
        scope: btn.getAttribute("data-scope") || "",
        id: btn.getAttribute("data-id") || "",
      })
        .then(function (data) {
          panel.textContent =
            data && data.summary ? data.summary : "No summary available.";
        })
        .catch(function (err) {
          panel.textContent =
            typeof err === "string" ? err : "Summary unavailable.";
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  }

  function init() {
    document.querySelectorAll("[data-rmc-ai-improve]").forEach(wireImprove);
    document.querySelectorAll("[data-rmc-ai-summarize]").forEach(wireSummarize);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
