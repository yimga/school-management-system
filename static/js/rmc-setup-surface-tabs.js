/**
 * rmc-setup-surface-tabs.js — wizard stage tabs for onboarding command surface.
 * Shows one lifecycle stage at a time so the admin backend stays within page-fold cap.
 */
(function () {
  "use strict";

  function initSetupSurfaceTabs() {
    document.querySelectorAll('[data-rmc-setup-wizards="1"]').forEach(function (host) {
      var surface = host.closest("[data-rmc-setup-surface]");
      if (!surface) return;
      var stages = host.querySelectorAll(".rmc-setup-surface__stage");
      if (!stages.length) return;
      var navLinks = surface.querySelectorAll(
        ".rmc-setup-surface__stage-nav [data-rmc-section-anchor]"
      );

      function showStage(stageId) {
        for (var i = 0; i < stages.length; i++) {
          var stage = stages[i];
          var on = stage.id === stageId;
          stage.hidden = !on;
          stage.setAttribute("aria-hidden", on ? "false" : "true");
        }
        for (var j = 0; j < navLinks.length; j++) {
          var link = navLinks[j];
          var href = link.getAttribute("href") || "";
          var active = href === "#" + stageId;
          link.classList.toggle("is-active", active);
          if (active) {
            link.setAttribute("aria-current", "page");
          } else {
            link.removeAttribute("aria-current");
          }
        }
      }

      showStage(stages[0].id);

      for (var k = 0; k < navLinks.length; k++) {
        (function (link) {
          link.addEventListener("click", function (ev) {
            ev.preventDefault();
            var href = link.getAttribute("href") || "";
            if (href.charAt(0) === "#") {
              showStage(href.slice(1));
            }
          });
        })(navLinks[k]);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSetupSurfaceTabs);
  } else {
    initSetupSurfaceTabs();
  }
})();
