/**
 * Offline capability vault — WebCrypto PIN wrap (SODP batch 1408).
 * Never stores password hashes or raw SMTP credentials.
 *
 * SECURE CONTEXT IS A HARD REQUIREMENT. Everything below goes through
 * `crypto.subtle`, which browsers expose ONLY in a secure context: HTTPS, or
 * `localhost`. A sovereign box reached at `http://10.10.20.137:10000` — plain
 * HTTP on an IP literal — is not one, so `crypto.subtle` is `undefined` there and
 * `deriveKey` throws `TypeError` on the first call.
 *
 * That failure used to surface as "Local access could not be enabled on this
 * browser", which is false and cost real debugging time: Chrome, Edge and Firefox
 * all implement WebCrypto correctly and are withholding it from an insecure
 * ORIGIN exactly as the spec requires. Changing browsers can never help. Because
 * sealing could never succeed, `loadSealed()` was always null and the "Continue in
 * local mode" button stayed hidden forever — offline continuity has never worked
 * on any HTTP box.
 *
 * `availability()` exists so callers can say the true reason, and can decline to
 * offer a feature that cannot work here rather than failing after the user has
 * chosen and confirmed a PIN.
 */
(function (global) {
  "use strict";

  const VAULT_KEY = "rmc_offline_capability_v1";

  /**
   * Can this ORIGIN do the crypto the vault needs?
   * @returns {{ok: boolean, reason: string, detail: string}}
   */
  function availability() {
    const secure = global.isSecureContext !== false;
    const subtle = !!(global.crypto && global.crypto.subtle);
    if (subtle && secure) return { ok: true, reason: "", detail: "" };
    if (!secure) {
      return {
        ok: false,
        reason: "insecure-context",
        detail:
          "Local access needs a secure (HTTPS) connection. This server is reached over " +
          "plain HTTP, so the browser will not allow the encryption this feature uses. " +
          "Ask your administrator to enable HTTPS on this server.",
      };
    }
    return {
      ok: false,
      reason: "no-webcrypto",
      detail:
        "This browser does not provide the Web Crypto API, so local access cannot be " +
        "secured on this device.",
    };
  }

  function assertAvailable() {
    const state = availability();
    if (!state.ok) {
      const error = new Error(state.detail);
      error.rmcReason = state.reason;
      throw error;
    }
  }

  async function deriveKey(pin, salt) {
    const enc = new TextEncoder();
    const baseKey = await crypto.subtle.importKey(
      "raw",
      enc.encode(pin),
      "PBKDF2",
      false,
      ["deriveKey"],
    );
    return crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt,
        iterations: 120000,
        hash: "SHA-256",
      },
      baseKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
  }

  async function sealCapability(pin, capabilityBlob) {
    assertAvailable();
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const key = await deriveKey(pin, salt);
    const enc = new TextEncoder();
    const cipher = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      enc.encode(capabilityBlob),
    );
    return {
      salt: Array.from(salt),
      iv: Array.from(iv),
      cipher: Array.from(new Uint8Array(cipher)),
    };
  }

  async function openCapability(pin, sealed) {
    assertAvailable();
    if (!sealed || !sealed.salt || !sealed.iv || !sealed.cipher) return null;
    const salt = new Uint8Array(sealed.salt);
    const iv = new Uint8Array(sealed.iv);
    const data = new Uint8Array(sealed.cipher);
    const key = await deriveKey(pin, salt);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, data);
    return new TextDecoder().decode(plain);
  }

  function saveSealed(sealed) {
    try {
      localStorage.setItem(VAULT_KEY, JSON.stringify(sealed));
    } catch (_e) {
      /* quota */
    }
  }

  function loadSealed() {
    try {
      const raw = localStorage.getItem(VAULT_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_e) {
      return null;
    }
  }

  global.RMCOfflineAuthVault = {
    availability,
    sealCapability,
    openCapability,
    saveSealed,
    loadSealed,
    VAULT_KEY,
  };
})(typeof window !== "undefined" ? window : globalThis);
