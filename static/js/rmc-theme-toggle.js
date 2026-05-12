/**
 * Theme toggle (Light / Dark / System) for the user dropdown.
 * Reads/writes via window.RMCTheme (theme-preference-bootstrap.js) so persistence
 * + live OS response are handled in one place.
 *
 * Markup contract (set in templates/components/user_dropdown.html):
 *   <button data-rmc-theme="light">…</button>
 *   <button data-rmc-theme="dark">…</button>
 *   <button data-rmc-theme="system">…</button>
 *   <span data-rmc-theme-current></span>
 */
(function () {
  "use strict";

  var LABELS = { light: "Light", dark: "Dark", system: "System" };

  function refresh() {
    if (!window.RMCTheme) { return; }
    var pref = window.RMCTheme.get();
    var resolved = window.RMCTheme.resolved();
    var buttons = document.querySelectorAll(".rmc-theme-btn[data-rmc-theme]");
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      var active = btn.getAttribute("data-rmc-theme") === pref;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    }
    var label = document.querySelector("[data-rmc-theme-current]");
    if (label) {
      label.textContent = pref === "system"
        ? "System · " + LABELS[resolved]
        : LABELS[pref] || "";
    }
  }

  function onClick(e) {
    var btn = e.target.closest && e.target.closest(".rmc-theme-btn[data-rmc-theme]");
    if (!btn) { return; }
    e.preventDefault();
    if (window.RMCTheme) {
      window.RMCTheme.set(btn.getAttribute("data-rmc-theme"));
    }
  }

  function init() {
    document.addEventListener("click", onClick, false);
    window.addEventListener("rmc:theme-change", refresh);
    refresh();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
