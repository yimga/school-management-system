/**
 * Page-context help: opens AI Center with first-line support + current URL.
 */
(function () {
  function aiCenterBase() {
    var data = document.getElementById("rmc-cmdk-data");
    if (!data) return "";
    try {
      return JSON.parse(data.textContent || "{}").ai_center_url || "";
    } catch (e) {
      return "";
    }
  }

  function openPageHelp() {
    var base = aiCenterBase();
    if (!base) return;
    var path =
      (typeof window !== "undefined" &&
        window.location &&
        (window.location.pathname || "") + (window.location.search || "")) ||
      "";
    var q = "How do I use this screen?";
    var sep = base.indexOf("?") >= 0 ? "&" : "?";
    window.location.href =
      base +
      sep +
      "assistant=first_line_support&q=" +
      encodeURIComponent(q) +
      "&active_url=" +
      encodeURIComponent(path);
  }

  document.addEventListener("click", function (e) {
    var target = e.target && e.target.closest ? e.target : null;
    var btn = target ? target.closest("[data-rmc-page-help]") : null;
    if (!btn) return;
    if (btn === document.body || btn === document.documentElement) return;
    e.preventDefault();
    openPageHelp();
  });
})();
