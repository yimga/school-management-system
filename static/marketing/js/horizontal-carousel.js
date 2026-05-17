/**
 * Keyboard-accessible horizontal scroll for logo carousels (Phase 3).
 */
(function () {
  function init(root) {
    var track = root.querySelector(".mkt-v3-logo-carousel__track");
    if (!track) return;
    root.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight") {
        track.scrollBy({ left: 120, behavior: "smooth" });
        e.preventDefault();
      } else if (e.key === "ArrowLeft") {
        track.scrollBy({ left: -120, behavior: "smooth" });
        e.preventDefault();
      }
    });
  }
  function boot() {
    document.querySelectorAll("[data-mkt-horizontal-carousel]").forEach(init);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
