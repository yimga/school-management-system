/**
 * Page-context help: copilot rail "?" → Help Center with active_url + contextual q.
 * Falls back to AI Center first-line support when help_center_url is unavailable.
 */
(function () {
  "use strict";

  function cmdkConfig() {
    var data = document.getElementById("rmc-cmdk-data");
    if (!data) {
      return {};
    }
    try {
      return JSON.parse(data.textContent || "{}");
    } catch (e) {
      return {};
    }
  }

  function activePath() {
    if (typeof window === "undefined" || !window.location) {
      return "";
    }
    return (window.location.pathname || "") + (window.location.search || "");
  }

  function contextualQuery() {
    var titleNode =
      document.querySelector(
        "[data-rmc-page-help-title], #cp-main-content h1, .cp-hero__title, .rmc-os-page-header h1, main h1"
      ) || null;
    var label = titleNode
      ? (titleNode.getAttribute("data-rmc-page-help-title") || titleNode.textContent || "").trim()
      : "";
    if (label) {
      return "How do I use " + label.replace(/\s+/g, " ") + "?";
    }
    var title = (document.title || "").split("|")[0].split("—")[0].trim();
    if (title && title.length > 2 && title.length < 120) {
      return "How do I use " + title + "?";
    }
    return "How do I use this screen?";
  }

  function buildHelpCenterUrl(base, path, query) {
    try {
      var url = new URL(base, window.location.origin);
      url.searchParams.set("from", "page_help");
      url.searchParams.set("active_url", path);
      if (query) {
        url.searchParams.set("q", query);
      }
      return url.pathname + url.search + url.hash;
    } catch (e) {
      var sep = base.indexOf("?") >= 0 ? "&" : "?";
      return (
        base +
        sep +
        "from=page_help&active_url=" +
        encodeURIComponent(path) +
        "&q=" +
        encodeURIComponent(query)
      );
    }
  }

  function buildAiCenterFallback(base, path, query) {
    var sep = base.indexOf("?") >= 0 ? "&" : "?";
    return (
      base +
      sep +
      "assistant=first_line_support&q=" +
      encodeURIComponent(query) +
      "&active_url=" +
      encodeURIComponent(path)
    );
  }

  function openPageHelp() {
    var cfg = cmdkConfig();
    var path = activePath();
    var query = contextualQuery();
    var helpBase = (cfg.help_center_url || "").trim();
    if (helpBase) {
      window.location.href = buildHelpCenterUrl(helpBase, path, query);
      return;
    }
    var aiBase = (cfg.ai_center_url || "").trim();
    if (aiBase) {
      window.location.href = buildAiCenterFallback(aiBase, path, query);
    }
  }

  document.addEventListener("click", function (e) {
    var target = e.target && e.target.closest ? e.target : null;
    var btn = target ? target.closest("[data-rmc-page-help]") : null;
    if (!btn) {
      return;
    }
    if (btn === document.body || btn === document.documentElement) {
      return;
    }
    e.preventDefault();
    openPageHelp();
  });
})();
