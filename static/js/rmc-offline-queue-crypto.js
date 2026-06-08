/**
 * AES-GCM queue body crypto for the service worker (batch 1651).
 * Loaded via importScripts from service-worker.js.
 */
(function (global) {
  "use strict";

  var PREFIX = "rmc-aes-gcm:v1:";
  var cached = null;

  function b64ToBytes(b64) {
    var bin = global.atob(b64);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
    return out;
  }

  function bytesToB64(bytes) {
    var bin = "";
    for (var i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
    return global.btoa(bin);
  }

  function resetKeyCache() {
    cached = null;
  }

  function importRawKey(b64) {
    if (!b64 || !global.crypto || !global.crypto.subtle) {
      return Promise.resolve(null);
    }
    if (cached && cached.b64 === b64) {
      return Promise.resolve(cached.key);
    }
    var raw = b64ToBytes(b64);
    return global.crypto.subtle
      .importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"])
      .then(function (key) {
        cached = { b64: b64, key: key };
        return key;
      });
  }

  function legacyDecrypt(body) {
    try {
      return decodeURIComponent(global.atob(body));
    } catch (_e) {
      return body;
    }
  }

  function encryptBody(body, keyB64) {
    if (typeof body !== "string") return Promise.resolve(body);
    return importRawKey(keyB64).then(function (key) {
      if (!key) {
        try {
          return global.btoa(encodeURIComponent(body));
        } catch (_e) {
          return body;
        }
      }
      var iv = global.crypto.getRandomValues(new Uint8Array(12));
      return global.crypto.subtle
        .encrypt({ name: "AES-GCM", iv: iv }, key, new TextEncoder().encode(body))
        .then(function (ct) {
          return PREFIX + bytesToB64(iv) + ":" + bytesToB64(new Uint8Array(ct));
        });
    });
  }

  function decryptBody(body, keyB64) {
    if (typeof body !== "string") return Promise.resolve(body);
    if (body.indexOf(PREFIX) === 0) {
      return importRawKey(keyB64).then(function (key) {
        if (!key) return body;
        var rest = body.slice(PREFIX.length);
        var parts = rest.split(":");
        if (parts.length < 2) return body;
        var iv = b64ToBytes(parts[0]);
        var ct = b64ToBytes(parts.slice(1).join(":"));
        return global.crypto.subtle
          .decrypt({ name: "AES-GCM", iv: iv }, key, ct)
          .then(function (pt) {
            return new TextDecoder().decode(pt);
          })
          .catch(function () {
            return body;
          });
      });
    }
    return Promise.resolve(legacyDecrypt(body));
  }

  global.RmcOfflineQueueCrypto = {
    PREFIX: PREFIX,
    encryptBody: encryptBody,
    decryptBody: decryptBody,
    resetKeyCache: resetKeyCache,
  };
})(self);
