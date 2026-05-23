/**
 * Dismiss launch splash after first paint (Phase 4).
 * Never remove [hidden] before dismiss — that exposes a full-viewport z-index
 * 10000 layer that blocks every click until .is-dismissed paints.
 */
(function () {
  function dismiss() {
    var el = document.getElementById("rmc-launch-splash");
    if (!el) return;
    el.classList.add("is-dismissed");
    el.setAttribute("aria-hidden", "true");
    el.style.pointerEvents = "none";
    window.setTimeout(function () {
      el.remove();
    }, 420);
  }

  var failSafe = window.setTimeout(function () {
    var el = document.getElementById("rmc-launch-splash");
    if (!el) return;
    el.style.pointerEvents = "none";
    el.remove();
  }, 2000);

  function dismissAndClear() {
    window.clearTimeout(failSafe);
    dismiss();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", dismissAndClear);
  } else {
    dismissAndClear();
  }
})();
