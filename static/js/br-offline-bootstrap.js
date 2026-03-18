/**
 * BR-03: Optional service worker registration for parent/teacher offline shell.
 * Include on high-traffic portal pages when PRODUCT_OFFLINE_PWA=1.
 */
(function () {
  if (!("serviceWorker" in navigator)) return;
  if (typeof window.BR_OFFLINE_SW === "string" && window.BR_OFFLINE_SW) {
    navigator.serviceWorker.register(window.BR_OFFLINE_SW).catch(function () {});
  }
})();
