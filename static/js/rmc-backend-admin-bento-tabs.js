/**
 * rmc-backend-admin-bento-tabs.js — post-onboarding admin dashboard bento tabs.
 * Keeps overview vs cockpit on separate panels to stay within page-fold cap.
 */
(function () {
  "use strict";

  function initAdminBento() {
    document.querySelectorAll("[data-rmc-admin-bento]").forEach(function (root) {
      var tabs = root.querySelectorAll("[data-rmc-admin-bento-tab]");
      var panels = root.querySelectorAll("[data-rmc-admin-bento-panel]");
      if (!tabs.length || !panels.length) return;

      function show(panelId) {
        for (var i = 0; i < panels.length; i++) {
          var panel = panels[i];
          var on = panel.id === panelId;
          panel.hidden = !on;
          panel.setAttribute("aria-hidden", on ? "false" : "true");
        }
        for (var j = 0; j < tabs.length; j++) {
          var tab = tabs[j];
          var href = tab.getAttribute("href") || "";
          var active = href === "#" + panelId;
          tab.classList.toggle("is-active", active);
          if (active) {
            tab.setAttribute("aria-current", "page");
          } else {
            tab.removeAttribute("aria-current");
          }
        }
      }

      show(panels[0].id);

      for (var k = 0; k < tabs.length; k++) {
        (function (tab) {
          tab.addEventListener("click", function (ev) {
            ev.preventDefault();
            var href = tab.getAttribute("href") || "";
            if (href.charAt(0) === "#") {
              show(href.slice(1));
            }
          });
        })(tabs[k]);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAdminBento);
  } else {
    initAdminBento();
  }
})();
