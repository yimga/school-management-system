/**
 * Offline capability vault — WebCrypto PIN wrap (SODP batch 1408).
 * Never stores password hashes or raw SMTP credentials.
 */
(function (global) {
  "use strict";

  const VAULT_KEY = "rmc_offline_capability_v1";

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
    sealCapability,
    openCapability,
    saveSealed,
    loadSealed,
    VAULT_KEY,
  };
})(typeof window !== "undefined" ? window : globalThis);
