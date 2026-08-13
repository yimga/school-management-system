(function () {
  "use strict";
  document.querySelectorAll("[data-rmc-account-center='1']").forEach(function (center) {
    if (center.dataset.rmcAccountBound === "1") return;
    center.dataset.rmcAccountBound = "1";
    var connectivity = center.querySelector("[data-rmc-account-connectivity]");
    var wrapper = center.closest(".user-dropdown-wrapper");
    var trigger = wrapper && wrapper.querySelector("[data-bs-toggle='dropdown']");
    function positionInViewport() {
      if (!center.classList.contains("show") || !trigger) return;
      var triggerRect = trigger.getBoundingClientRect();
      var rail = document.querySelector("[data-rmc-copilot-rail]");
      var railRect = rail && rail.getBoundingClientRect();
      var viewportGap = 8;
      var right = viewportGap;
      if (railRect && railRect.width > 0 && railRect.right > window.innerWidth - 2) {
        right = Math.max(viewportGap, window.innerWidth - railRect.left + viewportGap);
      }
      var top = Math.max(viewportGap, triggerRect.bottom + viewportGap);
      center.style.setProperty("--rmc-account-top", top + "px");
      center.style.setProperty("--rmc-account-right", right + "px");
      center.style.setProperty("--rmc-account-max-height", Math.max(160, window.innerHeight - top - viewportGap) + "px");
      center.dataset.rmcAccountViewportPositioned = "1";
    }
    function clearViewportPosition() {
      delete center.dataset.rmcAccountViewportPositioned;
      center.style.removeProperty("--rmc-account-top");
      center.style.removeProperty("--rmc-account-right");
      center.style.removeProperty("--rmc-account-max-height");
    }
    if (wrapper) {
      wrapper.addEventListener("shown.bs.dropdown", positionInViewport);
      wrapper.addEventListener("hidden.bs.dropdown", clearViewportPosition);
    }
    window.addEventListener("resize", positionInViewport, { passive: true });
    window.addEventListener("scroll", positionInViewport, { passive: true, capture: true });
    function updateConnectivity() {
      if (!connectivity) return;
      connectivity.textContent = navigator.onLine === false ? "Offline safe" : "Local ready";
      connectivity.title = navigator.onLine === false ? "Local preferences remain available" : "Local preferences are ready";
    }
    window.addEventListener("online", updateConnectivity);
    window.addEventListener("offline", updateConnectivity);
    updateConnectivity();
  });
})();
