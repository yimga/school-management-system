// Best-effort Web Push subscription for authenticated portal shells.
(function () {
  'use strict';

  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

  var boot = window.__RMC_WEB_PUSH_BOOT__;
  if (!boot || !boot.enabled || !boot.vapidUrl || !boot.subscribeUrl) return;

  function getCookie(name) {
    var parts = ('; ' + document.cookie).split('; ' + name + '=');
    if (parts.length === 2) {
      return parts.pop().split(';').shift();
    }
    return '';
  }

  function urlBase64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var raw = window.atob(base64);
    var output = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; ++i) {
      output[i] = raw.charCodeAt(i);
    }
    return output;
  }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken') || '',
      },
      body: JSON.stringify(body || {}),
    });
  }

  function maybeSubscribe(registration) {
    if (Notification.permission === 'denied') return Promise.resolve();
    return fetch(boot.vapidUrl, { credentials: 'same-origin' })
      .then(function (response) {
        return response.json();
      })
      .then(function (cfg) {
        if (!cfg || !cfg.configured || !cfg.public_key) return null;
        var permission = Notification.permission;
        if (permission === 'default') {
          return Notification.requestPermission().then(function (result) {
            if (result !== 'granted') return null;
            return cfg.public_key;
          });
        }
        if (permission !== 'granted') return null;
        return cfg.public_key;
      })
      .then(function (publicKey) {
        if (!publicKey) return null;
        return registration.pushManager.getSubscription().then(function (existing) {
          if (existing) {
            return postJson(boot.subscribeUrl, existing.toJSON());
          }
          return registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(publicKey),
          });
        });
      })
      .then(function (subscription) {
        if (!subscription || !subscription.toJSON) return;
        return postJson(boot.subscribeUrl, subscription.toJSON());
      })
      .catch(function () {
        /* subscription is best-effort */
      });
  }

  window.addEventListener('load', function () {
    navigator.serviceWorker.ready
      .then(maybeSubscribe)
      .catch(function () {});
  });
})();
