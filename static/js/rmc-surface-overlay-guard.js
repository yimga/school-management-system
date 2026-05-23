/**
 * Unblocks clicks when Unfold/Bootstrap leaves invisible overlays (manager + CP surfaces).
 * v3.62.13 (2026-05-22)
 */
(function () {
  "use strict";

  function isManagerSurface() {
    return (
      document.body &&
      (document.body.classList.contains("admin-manager-shell") ||
        document.body.classList.contains("control-plane-shell"))
    );
  }

  function sanitizeStuckOverlays() {
    var mo = document.getElementById("modal-overlay");
    if (mo && mo.classList.contains("hidden")) {
      var st = window.getComputedStyle(mo);
      if (st.display !== "none" && st.visibility !== "hidden") {
        mo.style.display = "none";
        mo.style.pointerEvents = "none";
      }
    }
    document.querySelectorAll(".modal-backdrop.show, .offcanvas-backdrop.show").forEach(function (bd) {
      if (bd && bd.parentNode) {
        bd.classList.remove("show");
        bd.remove();
      }
    });
  }

  function boot() {
    if (!isManagerSurface()) return;
    sanitizeStuckOverlays();
    window.setInterval(sanitizeStuckOverlays, 2500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
