/**
 * Parent dashboard PWA install CTA (CEZGP 1521).
 * Surfaces deferred install prompt when the browser offers it.
 */
(function () {
  "use strict";
  var deferredPrompt = null;
  var btn = document.getElementById("rmc-pwa-install-btn");
  var hint = document.getElementById("rmc-pwa-install-hint");
  if (!btn) {
    return;
  }
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredPrompt = e;
    btn.hidden = false;
    if (hint) {
      hint.hidden = true;
    }
  });
  btn.addEventListener("click", function () {
    if (!deferredPrompt) {
      return;
    }
    deferredPrompt.prompt();
    deferredPrompt.userChoice.finally(function () {
      deferredPrompt = null;
      btn.hidden = true;
    });
  });
})();
