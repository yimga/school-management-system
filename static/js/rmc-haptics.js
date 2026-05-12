/**
 * Tiny haptic / motion helper. Fires Navigator.vibrate() on mobile when callers
 * dispatch `rmc:success`, `rmc:warning`, or `rmc:error` CustomEvents.
 *
 * Respect prefers-reduced-motion: when the user opts out, haptics are also off
 * (the spec treats vibrations as motion).
 *
 * Usage:
 *   window.dispatchEvent(new CustomEvent('rmc:success'));
 */
(function () {
  "use strict";

  function reducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function vibrate(pattern) {
    if (reducedMotion()) { return; }
    if (typeof navigator === "undefined" || typeof navigator.vibrate !== "function") { return; }
    try { navigator.vibrate(pattern); } catch (_) {}
  }

  window.addEventListener("rmc:success", function () { vibrate([10]); });
  window.addEventListener("rmc:warning", function () { vibrate([20, 50, 20]); });
  window.addEventListener("rmc:error",   function () { vibrate([60, 40, 60]); });

  /* Auto-trigger success haptic when a toast-success appears. */
  if ("MutationObserver" in window) {
    var container = document.getElementById("toast-container");
    if (container) {
      new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          m.addedNodes.forEach(function (n) {
            if (!n.classList) { return; }
            if (n.classList.contains("toast-success")) { vibrate([10]); }
            if (n.classList.contains("toast-error") || n.classList.contains("toast-danger")) { vibrate([60, 40, 60]); }
          });
        });
      }).observe(container, { childList: true });
    }
  }
})();
