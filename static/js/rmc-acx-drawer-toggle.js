/**
 * Inline drawer toggle for [data-apple-class-quick-profile-drawer].
 *
 * The .rmc-acx-drawer component renders inline as a card. When
 * aria-expanded="false" (the default) we paint a compact one-line strip
 * (CSS in rmc-world-class-experience.css). Clicking the strip expands it
 * to the full panel; clicking the close affordance collapses it back.
 *
 * Without this script the drawer is stuck in its "false" rendering forever
 * — which is exactly what the user wants visually on the dashboard, but
 * the trailing button is still reachable for the action. The keyboard path
 * is preserved via tabindex on the <aside>.
 */
(function () {
  "use strict";

  function toggle(drawer) {
    var expanded = drawer.getAttribute("aria-expanded") === "true";
    drawer.setAttribute("aria-expanded", expanded ? "false" : "true");
  }

  function onClick(e) {
    if (!e.target.closest) { return; }
    /* If the user clicked the primary action button, don't intercept — let
       the link navigate normally. */
    if (e.target.closest(".btn")) { return; }
    var drawer = e.target.closest("[data-apple-class-quick-profile-drawer]");
    if (!drawer) { return; }
    toggle(drawer);
  }

  function onKey(e) {
    if (e.key !== "Enter" && e.key !== " ") { return; }
    if (!e.target.closest) { return; }
    var drawer = e.target.closest("[data-apple-class-quick-profile-drawer]");
    if (!drawer) { return; }
    /* Only fire when the drawer itself (not a child button/link) has focus. */
    if (document.activeElement !== drawer) { return; }
    e.preventDefault();
    toggle(drawer);
  }

  function init() {
    document.addEventListener("click", onClick, false);
    document.addEventListener("keydown", onKey, false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
