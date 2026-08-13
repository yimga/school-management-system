(function () {
  "use strict";
  document.querySelectorAll("[data-rmc-account-center='1']").forEach(function (center) {
    if (center.dataset.rmcAccountBound === "1") return;
    center.dataset.rmcAccountBound = "1";
    var connectivity = center.querySelector("[data-rmc-account-connectivity]");
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
