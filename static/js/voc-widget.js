// VOC feedback — works standalone (.voc-widget) or inside assist dock (.rmc-assist-panel--feedback).
(function () {
  function bindToggle(toggle) {
    if (!toggle || toggle.dataset.vocBound) return;
    toggle.dataset.vocBound = "1";
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      var panel =
        document.querySelector(".rmc-assist-panel--feedback") ||
        toggle.closest(".voc-widget");
      if (!panel) return;

      if (panel.classList.contains("rmc-assist-panel--feedback")) {
        var open = panel.classList.toggle("rmc-assist-panel--open");
        panel.dataset.open = open ? "true" : "false";
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        if (window.RMCAssistDock) {
          if (open) {
            window.RMCAssistDock.closeAll("feedback");
            document.body.setAttribute("data-rmc-assist-panel", "feedback");
          } else {
            window.RMCAssistDock.closeAll();
          }
          window.RMCAssistDock.syncBackdrop();
        }
        return;
      }

      var widget = toggle.closest(".voc-widget");
      if (!widget) return;
      widget.dataset.open = widget.dataset.open === "true" ? "false" : "true";
      toggle.setAttribute(
        "aria-expanded",
        widget.dataset.open === "true" ? "true" : "false"
      );
    });
  }

  function init() {
    document.querySelectorAll("[data-voc-toggle], [data-rmc-assist-feedback-toggle]").forEach(bindToggle);
    document.querySelectorAll(".voc-widget [data-voc-close]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var panel = document.querySelector(".rmc-assist-panel--feedback");
        if (panel) {
          panel.classList.remove("rmc-assist-panel--open");
          panel.dataset.open = "false";
        }
        var toggle = document.querySelector("[data-rmc-assist-feedback-toggle]");
        if (toggle) toggle.setAttribute("aria-expanded", "false");
        if (window.RMCAssistDock) window.RMCAssistDock.closeAll();
      });
    });
  }

  window.__rmcVocReinit = init;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
