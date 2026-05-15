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
  var AESTHETIC_KEY = "runmycampus-aesthetic-preference";
  var AESTHETIC_VALID = { "warm-bright": 1, "cool-apple": 1, "stone": 1 };
  var AESTHETIC_LABELS = { "warm-bright": "Warm Bright", "cool-apple": "Cool Apple", "stone": "Stone" };

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

  function readAestheticPref() {
    var raw = null;
    try { raw = localStorage.getItem(AESTHETIC_KEY); } catch (_) { /* private mode */ }
    if (raw && AESTHETIC_VALID[raw]) { return raw; }
    /* Fall back to whatever the bootstrap projected. */
    var attr = document.documentElement.getAttribute("data-rmc-aesthetic");
    return AESTHETIC_VALID[attr] ? attr : "warm-bright";
  }

  function setAestheticPref(value) {
    if (!AESTHETIC_VALID[value]) { return; }
    try { localStorage.setItem(AESTHETIC_KEY, value); } catch (_) { /* private mode */ }
    try {
      window.dispatchEvent(new CustomEvent("rmc:aesthetic-change", { detail: { value: value } }));
    } catch (_) { /* old browser */ }
    refreshAesthetic();
  }

  function refreshAesthetic() {
    var current = readAestheticPref();
    var buttons = document.querySelectorAll(".rmc-aesthetic-btn[data-rmc-aesthetic]");
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      var active = btn.getAttribute("data-rmc-aesthetic") === current;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    }
    var label = document.querySelector("[data-rmc-aesthetic-current]");
    if (label) { label.textContent = AESTHETIC_LABELS[current] || ""; }
  }

  function onClick(e) {
    if (!e.target.closest) { return; }
    var themeBtn = e.target.closest(".rmc-theme-btn[data-rmc-theme]");
    if (themeBtn) {
      e.preventDefault();
      if (window.RMCTheme) {
        window.RMCTheme.set(themeBtn.getAttribute("data-rmc-theme"));
      }
      return;
    }
    var aestheticBtn = e.target.closest(".rmc-aesthetic-btn[data-rmc-aesthetic]");
    if (aestheticBtn) {
      e.preventDefault();
      setAestheticPref(aestheticBtn.getAttribute("data-rmc-aesthetic"));
    }
  }

  function init() {
    document.addEventListener("click", onClick, false);
    window.addEventListener("rmc:theme-change", refresh);
    window.addEventListener("rmc:aesthetic-change", refreshAesthetic);
    refresh();
    refreshAesthetic();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
