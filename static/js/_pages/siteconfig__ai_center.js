/**
 * AI Center page: swap the chat form's data-ai-url + studio-mode when the
 * operator picks a different assistant. The chat behavior itself is owned by
 * rmc_ai_guided_assistant.js (already loaded by the page).
 */
(function () {
  var MAX_TRANSCRIPT = 10;

  function clearTranscript(root) {
    if (!root) return;
    var wrap = root.querySelector("[data-rmc-ai-transcript-wrap]");
    var list = root.querySelector("[data-rmc-ai-transcript]");
    if (list) list.innerHTML = "";
    if (wrap) wrap.classList.add("d-none");
  }

  function appendTranscript(root, question, answer) {
    if (!root || !question) return;
    var wrap = root.querySelector("[data-rmc-ai-transcript-wrap]");
    var list = root.querySelector("[data-rmc-ai-transcript]");
    if (!list || !wrap) return;
    var item = document.createElement("li");
    item.className = "mb-2";
    var q = document.createElement("div");
    q.className = "fw-semibold";
    q.textContent = question;
    var a = document.createElement("div");
    a.className = "text-muted";
    a.textContent = answer || "(no summary)";
    item.appendChild(q);
    item.appendChild(a);
    list.appendChild(item);
    while (list.children.length > MAX_TRANSCRIPT) {
      list.removeChild(list.firstChild);
    }
    wrap.classList.remove("d-none");
  }

  function reset(form) {
    if (!form) return;
    var ta = form.querySelector("[data-rmc-ai-query]");
    var out = form.querySelector("[data-rmc-ai-out]");
    if (ta) ta.value = "";
    if (out) {
      out.textContent = "";
      out.hidden = true;
    }
    form.removeAttribute("data-rmc-ai-bound");
  }

  function pick(btn) {
    var root = btn.closest("[data-rmc-ai-center]");
    if (!root) return;
    var form = root.querySelector("[data-rmc-ai-guided]");
    var label = root.querySelector("[data-rmc-ai-center-label]");
    var hint = root.querySelector("[data-rmc-ai-center-hint]");

    var apiUrl = btn.getAttribute("data-api-url") || "";
    var mode = btn.getAttribute("data-studio-mode") || "";
    if (form) {
      form.setAttribute("data-ai-url", apiUrl);
      if (mode) {
        form.setAttribute("data-studio-mode", mode);
      } else {
        form.removeAttribute("data-studio-mode");
      }
      var ta = form.querySelector("[data-rmc-ai-query]");
      var runBtn = form.querySelector("[data-rmc-ai-run]");
      if (ta) {
        ta.disabled = false;
        ta.removeAttribute("aria-disabled");
        ta.setAttribute("placeholder", "What should we verify or do next?");
      }
      if (runBtn) {
        runBtn.disabled = false;
        runBtn.removeAttribute("aria-disabled");
      }
      reset(form);
      clearTranscript(root);
    }
    if (label) label.textContent = btn.getAttribute("data-label") || "";
    if (hint) hint.textContent = btn.getAttribute("data-hint") || "";

    root.querySelectorAll("[data-rmc-ai-center-pick]").forEach(function (el) {
      el.setAttribute("aria-selected", el === btn ? "true" : "false");
    });

    /* Re-bind chat handlers on the swapped form. */
    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(function () {
        document.dispatchEvent(new Event("rmc:ai-guided-rebind"));
      });
    }
  }

  document.addEventListener("rmc:ai-guided-answered", function (e) {
    var root = document.querySelector("[data-rmc-ai-center]");
    var d = e.detail || {};
    appendTranscript(root, d.question, d.answer);
  });

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-rmc-ai-center-pick]");
    if (!btn || btn.disabled) return;
    pick(btn);
  });

  function syncBrowserOffline() {
    var hint = document.querySelector("[data-rmc-ai-browser-offline]");
    var form = document.querySelector("[data-rmc-ai-center] [data-rmc-ai-guided]");
    var runBtn = form && form.querySelector("[data-rmc-ai-run]");
    var offline = typeof navigator !== "undefined" && navigator.onLine === false;
    if (hint) {
      if (offline) {
        hint.classList.remove("d-none");
      } else {
        hint.classList.add("d-none");
      }
    }
    if (runBtn) {
      runBtn.disabled = offline;
    }
  }

  window.addEventListener("online", syncBrowserOffline);
  window.addEventListener("offline", syncBrowserOffline);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncBrowserOffline);
  } else {
    syncBrowserOffline();
  }
})();
