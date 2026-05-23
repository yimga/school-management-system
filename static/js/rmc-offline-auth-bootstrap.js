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
    if (hubBaseUrl() && window.RMCLanMuleSync && window.RMCLanMuleSync.noteHubOnline) {
      window.RMCLanMuleSync.noteHubOnline(hubBaseUrl());
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", refreshCapabilityIfOnline);
  } else {
    refreshCapabilityIfOnline();
  }
})();
