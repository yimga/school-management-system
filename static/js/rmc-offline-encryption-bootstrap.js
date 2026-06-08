/**
 * Fetch session-scoped queue encryption key after SMS_OFFLINE_CONFIG loads.
 * Dispatches rmc-offline-config-ready when config (and optional key) is ready.
 */
(function () {
  "use strict";

  function signalReady() {
    try {
      window.dispatchEvent(new CustomEvent("rmc-offline-config-ready"));
    } catch (_e) {
      /* IE11 guard — not a target */
    }
  }

  var cfg = window.SMS_OFFLINE_CONFIG || {};
  if (!cfg.encryptOutbox || !cfg.encryptionKeyUrl) {
    signalReady();
    return;
  }

  fetch(cfg.encryptionKeyUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
    .then(function (res) {
      if (!res.ok) throw new Error("encryption key fetch failed");
      return res.json();
    })
    .then(function (data) {
      if (data && data.key_b64) {
        cfg.enableQueueEncryption = true;
        cfg.queueEncryptionKey = data.key_b64;
        window.SMS_OFFLINE_CONFIG = cfg;
      }
      signalReady();
    })
    .catch(function () {
      signalReady();
    });
})();
