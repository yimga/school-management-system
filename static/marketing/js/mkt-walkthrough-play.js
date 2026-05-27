/**
 * Walkthrough chapter reel — scroll to portal video and play on click.
 */
(function () {
  "use strict";

  function boot() {
    document.querySelectorAll("[data-mkt-walkthrough-play]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        if (btn.tagName === "BUTTON") {
          ev.preventDefault();
        }
        var chapter = btn.getAttribute("data-mkt-walkthrough-chapter");
        if (chapter) {
          document.querySelectorAll("[data-mkt-walkthrough-chapter]").forEach(function (el) {
            el.classList.remove("is-active");
            el.setAttribute("aria-current", "false");
          });
          btn.classList.add("is-active");
          btn.setAttribute("aria-current", "true");
        }
        var portal = document.getElementById("mkt-walkthrough-portal");
        if (!portal) return;
        portal.scrollIntoView({ behavior: "smooth", block: "center" });
        var overlay = portal.querySelector("[data-mkt-video-overlay]");
        if (overlay && !overlay.hidden) {
          overlay.click();
          return;
        }
        var toggle = portal.querySelector("[data-mkt-video-toggle]");
        if (toggle) toggle.click();
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
