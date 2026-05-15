// PWA service-worker registration. Reads the SW URL from a JSON data island
// (since {% static %} resolves it server-side) and reads the offline config
// that sms-offline-config-loader.js already populated on window.
// CSP-safe replacement for the previous inline script in portal_base.html.
(function () {
  var cfg = window.SMS_OFFLINE_CONFIG || {};
  var swEligible = cfg.pwaEnabled && (cfg.enabled || cfg.parentPortalShell);
  if (!('serviceWorker' in navigator) || !swEligible) return;

  var swEl = document.getElementById('rmc-service-worker-url');
  if (!swEl) return;
  var swUrl;
  try {
    var swCfg = JSON.parse(swEl.textContent || '{}');
    swUrl = swCfg.url || '';
  } catch (_e) {
    return;
  }
  if (!swUrl) return;

  function pushConfigToWorker(registration) {
    var payload = { type: 'SET_OFFLINE_CONFIG', payload: cfg };
    if (registration.active) registration.active.postMessage(payload);
    if (registration.waiting) registration.waiting.postMessage(payload);
    if (registration.installing) registration.installing.postMessage(payload);
  }

  // Track whether THIS page load was caused by the new SW taking over.
  // Prevents an infinite reload loop when a new SW activates on every visit.
  var reloadingForUpdate = false;
  navigator.serviceWorker.addEventListener('controllerchange', function () {
    if (reloadingForUpdate) return;
    reloadingForUpdate = true;
    window.location.reload();
  });

  window.addEventListener('load', function () {
    // updateViaCache: 'none' forces the browser to ALWAYS fetch service-worker.js
    // from the network on registration (not from the HTTP cache). Without this,
    // the SW file can stay cached for up to 24 hours, which means template /
    // CSS / JS fixes never reach users even after we bump CACHE_VERSION.
    navigator.serviceWorker.register(swUrl, { updateViaCache: 'none' })
      .then(function (registration) {
        try { console.log('Service Worker registered successfully:', registration.scope); } catch (_e) {}
        pushConfigToWorker(registration);

        // Aggressively check for an update on every page load. Cheap (one
        // HEAD/GET of service-worker.js); critical for getting fixes out.
        try { registration.update(); } catch (_e) {}

        if (cfg.requestPersistentStorage && navigator.storage && navigator.storage.persist) {
          navigator.storage.persist().catch(function () {});
        }

        // If a new SW is already waiting at registration time, activate it
        // immediately. Pairs with self.skipWaiting() in service-worker.js.
        if (registration.waiting && navigator.serviceWorker.controller) {
          registration.waiting.postMessage({ type: 'SKIP_WAITING' });
        }

        registration.addEventListener('updatefound', function () {
          var newWorker = registration.installing;
          if (!newWorker) return;
          newWorker.addEventListener('statechange', function () {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              // New SW installed while old SW is still controlling this page.
              // Tell the new SW to skip waiting → controllerchange fires → reload.
              try { newWorker.postMessage({ type: 'SKIP_WAITING' }); } catch (_e) {}
            }
          });
        });
      })
      .catch(function (error) {
        try { console.log('Service Worker registration failed:', error); } catch (_e) {}
      });
  });
})();
