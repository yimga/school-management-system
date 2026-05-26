// PWA service-worker registration. Reads the SW URL from a JSON data island
// (since {% static %} resolves it server-side) and reads the offline config
// that sms-offline-config-loader.js already populated on window.
// CSP-safe replacement for the previous inline script in portal_base.html.
//
// v2.46 (2026-05-15): "Updates available" toast UX — when a new SW installs
// while a controlled tab has dirty forms, do NOT silently reload. Show a
// persistent toast so the user can save first. When forms are clean, show a
// brief notice and auto-reload after a short pause.
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

  function anyDirtyForm() {
    try {
      return !!document.querySelector("form[data-rmc-dirty-watch][data-dirty='1']");
    } catch (_e) { return false; }
  }

  function ensureToastHost() {
    var host = document.querySelector('.rmc-toast-host');
    if (host) return host;
    host = document.createElement('div');
    host.className = 'rmc-toast-host';
    host.setAttribute('role', 'region');
    host.setAttribute('aria-live', 'polite');
    host.setAttribute('aria-label', 'Notifications');
    document.body.appendChild(host);
    return host;
  }

  function showUpdateToast(waitingWorker) {
    var host = ensureToastHost();
    // Don't stack duplicate update toasts.
    if (host.querySelector('[data-rmc-sw-update-toast]')) return;
    var toast = document.createElement('div');
    toast.className = 'rmc-toast rmc-toast--info';
    toast.setAttribute('data-rmc-sw-update-toast', '1');
    toast.setAttribute('role', 'status');
    toast.style.display = 'flex';
    toast.style.alignItems = 'center';
    toast.style.gap = '0.6rem';
    var msg = document.createElement('span');
    msg.style.flex = '1';
    msg.textContent = anyDirtyForm()
      ? 'Update available. Save your changes, then click Refresh.'
      : 'Update available — refresh to apply.';
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = 'Refresh';
    btn.className = 'btn btn-sm btn-primary';
    btn.style.flexShrink = '0';
    btn.addEventListener('click', function () {
      try { waitingWorker.postMessage({ type: 'SKIP_WAITING' }); } catch (_e) {}
    });
    toast.appendChild(msg);
    toast.appendChild(btn);
    host.appendChild(toast);
  }

  // Track whether THIS page load was caused by the new SW taking over.
  // Prevents an infinite reload loop when a new SW activates on every visit.
  var reloadingForUpdate = false;
  navigator.serviceWorker.addEventListener('controllerchange', function () {
    if (reloadingForUpdate) return;
    reloadingForUpdate = true;
    window.location.reload();
  });

  function handleWaiting(registration) {
    var waiting = registration.waiting;
    if (!waiting) return;
    // First-load (no controller yet) → silent activation is fine; the user
    // hasn't typed anything. Only show the toast when there's an active
    // controller that might be servicing in-flight work.
    if (!navigator.serviceWorker.controller) {
      try { waiting.postMessage({ type: 'SKIP_WAITING' }); } catch (_e) {}
      return;
    }
    if (anyDirtyForm()) {
      showUpdateToast(waiting);
    } else {
      // Clean tab → show a 2s notice then take over.
      showUpdateToast(waiting);
      setTimeout(function () {
        try { waiting.postMessage({ type: 'SKIP_WAITING' }); } catch (_e) {}
      }, 1500);
    }
  }

  window.addEventListener('load', function () {
    // updateViaCache: 'none' forces the browser to ALWAYS fetch service-worker.js
    // from the network on registration (not from the HTTP cache). Without this,
    // the SW file can stay cached for up to 24 hours, which means template /
    // CSS / JS fixes never reach users even after we bump CACHE_VERSION.
    navigator.serviceWorker.register(swUrl, { updateViaCache: 'none' })
      .then(function (registration) {
        pushConfigToWorker(registration);

        // Aggressively check for an update on every page load. Cheap (one
        // HEAD/GET of service-worker.js); critical for getting fixes out.
        try { registration.update(); } catch (_e) {}

        if (cfg.requestPersistentStorage && navigator.storage && navigator.storage.persist) {
          navigator.storage.persist().catch(function () {});
        }

        // A SW was already waiting when we arrived — surface it.
        if (registration.waiting) {
          handleWaiting(registration);
        }

        registration.addEventListener('updatefound', function () {
          var newWorker = registration.installing;
          if (!newWorker) return;
          newWorker.addEventListener('statechange', function () {
            if (newWorker.state === 'installed') {
              handleWaiting(registration);
            }
          });
        });
      })
      .catch(function (error) {
        try { console.warn('Service Worker registration failed:', error); } catch (_e) {}
      });
  });
})();
