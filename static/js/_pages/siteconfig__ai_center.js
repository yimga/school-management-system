/**
 * AI Center page: swap the chat form's data-ai-url + studio-mode when the
 * operator picks a different assistant. The chat behavior itself is owned by
 * rmc_ai_guided_assistant.js (already loaded by the page).
 */
(function () {
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
      reset(form);
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
