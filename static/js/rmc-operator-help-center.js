/**
 * Operator Help Center — focus search on "?" when not typing in a field;
 * apply page-aware context from copilot rail (from=page_help&active_url=&q=).
 */
(function () {
  "use strict";

  function rootEl() {
    return document.querySelector("[data-rmc-page='help-center']");
  }

  function isTypingTarget(el) {
    if (!el || !el.tagName) {
      return false;
    }
    var tag = el.tagName.toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
  }

  function applyInboundPageHelp() {
    var root = rootEl();
    if (!root) {
      return;
    }
    var params;
    try {
      params = new URLSearchParams(window.location.search || "");
    } catch (e) {
      return;
    }
    var activeUrl = (params.get("active_url") || "").trim();
    var q = (params.get("q") || "").trim();
    var fromPageHelp = params.get("from") === "page_help";

    if (activeUrl) {
      root.setAttribute("data-rmc-help-active-url", activeUrl);
    }

    var input = root.querySelector("[data-rmc-help-search-input]");
    if (input && q) {
      input.value = q;
    }

    var aiPrompt = root.querySelector("#rmc-kb-ai-prompt");
    if (aiPrompt && q && !aiPrompt.value) {
      aiPrompt.value = q;
    }

    if (activeUrl) {
      var hero = root.querySelector(".rmc-kb-operator__hero") || root;
      if (hero && !hero.querySelector("[data-rmc-page-help-context]")) {
        var labelText =
          root.getAttribute("data-rmc-page-help-context-label") || "Help for this page:";
        var strip = document.createElement("div");
        strip.className = "alert alert-info py-2 px-3 mb-3 small";
        strip.setAttribute("data-rmc-page-help-context", "1");
        strip.setAttribute("role", "status");
        var label = document.createElement("strong");
        label.textContent = labelText + " ";
        var code = document.createElement("code");
        code.textContent = activeUrl;
        strip.appendChild(label);
        strip.appendChild(code);
        var cardBody = hero.querySelector(".card-body") || hero;
        cardBody.insertBefore(strip, cardBody.firstChild);
      }
    }

    if (fromPageHelp && input) {
      input.focus();
      if (input.scrollIntoView) {
        input.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "?" || ev.ctrlKey || ev.metaKey || ev.altKey) {
      return;
    }
    if (isTypingTarget(ev.target)) {
      return;
    }
    var root = rootEl();
    if (!root) {
      return;
    }
    var input = root.querySelector("[data-rmc-help-search-input]");
    if (!input) {
      return;
    }
    ev.preventDefault();
    input.focus();
    input.select();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyInboundPageHelp);
  } else {
    applyInboundPageHelp();
  }
})();
