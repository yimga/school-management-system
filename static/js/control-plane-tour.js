/**
 * @deprecated Use rmc-tour.js (loaded via rmc_tour_bootstrap.html). Kept for cache URLs that still reference this file.
 */
(function () {
  function boot() {
    if (window.RMCTour && RMCTour.initControlPlane) {
      RMCTour.initControlPlane();
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
