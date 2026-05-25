/**
 * Portal bootstrap for offline capability vault (SODP batch 1413).
 * Loads after rmc-offline-auth-vault.js; exposes a gentle reconnect hook.
 */
(function () {
  "use strict";

  function cfg() {
    return window.SMS_OFFLINE_CONFIG || {};
  }

  function hubBaseUrl() {
    var c = cfg();
    return (c.hubBaseUrl || "").trim().replace(/\/$/, "");
  }

  function getDeviceId() {
    var storageKey = "rmc_offline_device_id";
    try {
      var existing = localStorage.getItem(storageKey);
      if (existing && existing.length >= 8) return existing.slice(0, 128);
      var generated =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? "web-" + crypto.randomUUID()
          : "web-" + Date.now() + "-" + Math.random().toString(36).slice(2, 12);
      localStorage.setItem(storageKey, generated.slice(0, 128));
      return localStorage.getItem(storageKey) || generated.slice(0, 128);
    } catch (_e) {
      return "web-anon-" + Date.now();
    }
  }

  function registerDeviceProvision() {
    if (!navigator.onLine) return;
    if (typeof window.rmcOfflineEnqueue !== "function") return;
    var deviceId = getDeviceId();
    if (!deviceId || deviceId.length < 8) return;
    window.rmcOfflineEnqueue({
      action_type: "provision.signup",
      payload: { device_id: deviceId },
      idempotency_key: ("provision-" + deviceId).slice(0, 128),
    });
  }

  async function refreshCapabilityIfOnline() {
    if (!navigator.onLine) return;
    if (!window.RMCOfflineAuthVault || !window.RMCOfflineAuthVault.loadSealed()) return;
    var mintUrl = cfg().offlineTokenMintUrl || cfg().offline_token_mint_url;
    if (!mintUrl) return;
    try {
      var res = await fetch(mintUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ purpose: "offline_capability_refresh" }),
      });
      if (!res.ok) return;
      var data = await res.json();
      if (window.RMCIamSnapshot && window.RMCIamSnapshot.applyMintResponse) {
        window.RMCIamSnapshot.applyMintResponse(data);
      }
      if (data && data.capability_blob_b64 && window.RMCOfflineAuthVault.saveSealed) {
        window.RMCOfflineAuthVault.saveSealed({
          blob_b64: data.capability_blob_b64,
          minted_at: new Date().toISOString(),
        });
      }
    } catch (_e) {
      /* non-fatal */
    }
  }

  window.addEventListener("online", function () {
    refreshCapabilityIfOnline();
    registerDeviceProvision();
    if (hubBaseUrl() && window.RMCLanMuleSync && window.RMCLanMuleSync.noteHubOnline) {
      window.RMCLanMuleSync.noteHubOnline(hubBaseUrl());
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      refreshCapabilityIfOnline();
      registerDeviceProvision();
    });
  } else {
    refreshCapabilityIfOnline();
    registerDeviceProvision();
  }
})();
