/**
 * IndexedDB crypto-at-rest wrapper.
 *
 * 12-pillar audit P9 follow-up. Offline-queued records (attendance,
 * notes, grades) live in IndexedDB and persist across browser
 * sessions. Without encryption-at-rest, an attacker with access to
 * the device can read the queue using devtools.
 *
 * This module wraps an IndexedDB store with AES-GCM encryption keyed
 * to a per-origin random key persisted in `localStorage` under
 * `rmc.offline.crypto.key.v1`. The key is generated lazily; rotating
 * it is a single localStorage.removeItem() away (operator console).
 *
 * Limitations honestly stated:
 *   * The key is in localStorage -- same origin XSS can read it.
 *     SRI + CSP (P1) are the upstream defenses; this wrapper raises
 *     the bar against casual devtools inspection, not against a
 *     determined attacker with script-execution privilege.
 *   * SubtleCrypto is required (HTTPS or localhost). On insecure
 *     contexts the wrapper exposes plaintext fall-back to avoid
 *     breaking dev / local previews -- the operator runbook flags
 *     this in DEPLOY_PIPELINE_RUNBOOK.
 *
 * API:
 *   const wrap = createOfflineCryptoWrapper();
 *   await wrap.ready;                       // ensures key + crypto
 *   const blob = await wrap.encrypt(obj);   // returns { iv, ciphertext }
 *   const obj  = await wrap.decrypt(blob);  // returns original
 *
 * Consumers (e.g. offline-queue-client.js) call wrap.encrypt before
 * idb.put and wrap.decrypt after idb.get; the wrapper itself does
 * NOT mutate IndexedDB -- that's the queue's responsibility.
 */
(function (global) {
  "use strict";

  const KEY_NAME = "rmc.offline.crypto.key.v1";
  const ALGO = { name: "AES-GCM", length: 256 };
  const IV_LEN = 12;

  function _hasSubtleCrypto() {
    return (
      typeof global !== "undefined" &&
      global.crypto &&
      global.crypto.subtle &&
      typeof global.crypto.getRandomValues === "function"
    );
  }

  function _bytesToB64(bytes) {
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return global.btoa(bin);
  }

  function _b64ToBytes(b64) {
    const bin = global.atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  async function _loadOrCreateKey() {
    const stored = global.localStorage && global.localStorage.getItem(KEY_NAME);
    if (stored) {
      try {
        const raw = _b64ToBytes(stored);
        return await global.crypto.subtle.importKey(
          "raw",
          raw,
          ALGO,
          false,
          ["encrypt", "decrypt"]
        );
      } catch (e) {
        // Corrupt stored key — regenerate.
      }
    }
    const key = await global.crypto.subtle.generateKey(ALGO, true, [
      "encrypt",
      "decrypt",
    ]);
    if (global.localStorage) {
      try {
        const raw = new Uint8Array(
          await global.crypto.subtle.exportKey("raw", key)
        );
        global.localStorage.setItem(KEY_NAME, _bytesToB64(raw));
      } catch (e) {
        // localStorage quota / privacy mode — accept transient key.
      }
    }
    return key;
  }

  function _encoder() {
    return new TextEncoder();
  }

  function _decoder() {
    return new TextDecoder();
  }

  function createOfflineCryptoWrapper() {
    const supported = _hasSubtleCrypto();
    if (!supported) {
      // Fail-open shim. The plaintext path keeps offline functionality
      // alive on insecure origins (dev / file://); operators MUST
      // serve production over HTTPS.
      return {
        supported: false,
        ready: Promise.resolve(false),
        async encrypt(obj) {
          return { plaintext: JSON.stringify(obj), iv: null, ciphertext: null };
        },
        async decrypt(blob) {
          if (blob && blob.plaintext !== undefined) {
            return JSON.parse(blob.plaintext);
          }
          throw new Error("offline-crypto-wrapper: cannot decrypt without SubtleCrypto");
        },
      };
    }
    let keyPromise = null;
    return {
      supported: true,
      ready: Promise.resolve(true),
      async encrypt(obj) {
        if (!keyPromise) keyPromise = _loadOrCreateKey();
        const key = await keyPromise;
        const iv = global.crypto.getRandomValues(new Uint8Array(IV_LEN));
        const plaintext = _encoder().encode(JSON.stringify(obj));
        const ciphertext = new Uint8Array(
          await global.crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext)
        );
        return {
          iv: _bytesToB64(iv),
          ciphertext: _bytesToB64(ciphertext),
        };
      },
      async decrypt(blob) {
        if (!blob) throw new Error("offline-crypto-wrapper: empty blob");
        if (blob.plaintext !== undefined) {
          return JSON.parse(blob.plaintext);
        }
        if (!keyPromise) keyPromise = _loadOrCreateKey();
        const key = await keyPromise;
        const iv = _b64ToBytes(blob.iv);
        const ct = _b64ToBytes(blob.ciphertext);
        const plaintext = await global.crypto.subtle.decrypt(
          { name: "AES-GCM", iv },
          key,
          ct
        );
        return JSON.parse(_decoder().decode(plaintext));
      },
      // Operator-side: clear the key (forces re-generation on next encrypt).
      async rotateKey() {
        if (global.localStorage) {
          global.localStorage.removeItem(KEY_NAME);
        }
        keyPromise = null;
      },
    };
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { createOfflineCryptoWrapper };
  } else {
    global.RmcOfflineCrypto = { createOfflineCryptoWrapper };
  }
})(typeof window !== "undefined" ? window : globalThis);
