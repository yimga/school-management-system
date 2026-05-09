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

  window.addEventListener('load', function () {
    navigator.serviceWorker.register(swUrl)
      .then(function (registration) {
        try { console.log('Service Worker registered successfully:', registration.scope); } catch (_e) {}
        pushConfigToWorker(registration);

        if (cfg.requestPersistentStorage && navigator.storage && navigator.storage.persist) {
          navigator.storage.persist().catch(function () {});
        }

        registration.addEventListener('updatefound', function () {
          var newWorker = registration.installing;
          newWorker.addEventListener('statechange', function () {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              if (window.confirm('A new version is available. Reload to update?')) {
                window.location.reload();
              }
            }
          });
        });
      })
      .catch(function (error) {
        try { console.log('Service Worker registration failed:', error); } catch (_e) {}
      });
  });
})();
