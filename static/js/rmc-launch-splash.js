/**
 * Dismiss launch splash after first paint (Phase 4).
 */
(function () {
  function dismiss() {
    var el = document.getElementById("rmc-launch-splash");
    if (!el) return;
    el.removeAttribute("hidden");
    el.setAttribute("aria-hidden", "false");
    requestAnimationFrame(function () {
      el.classList.add("is-dismissed");
      setTimeout(function () {
        el.remove();
      }, 400);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", dismiss);
  } else {
    dismiss();
  }
})();
