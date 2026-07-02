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

  // CSRF for the mint POST. DOM first: with CSRF_COOKIE_HTTPONLY=True the
  // csrftoken cookie is invisible to JS, so the rendered form input / meta tag
  // are the reliable sources (same pattern as offline-queue-client.js).
  function csrfToken() {
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (input && input.value) return input.value;
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.getAttribute("content")) return meta.getAttribute("content");
    try {
      var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : "";
    } catch (_e) {
      return "";
    }
  }

  var MINT_STATE_KEY = "rmc_offline_capability_mint_state";

  // Re-mint at half-life of the server-issued TTL so the device-bound IAM
  // snapshot never expires while the browser has connectivity, without
  // minting a token row on every page load.
  function mintDue() {
    try {
      var raw = localStorage.getItem(MINT_STATE_KEY);
      if (!raw) return true;
      var st = JSON.parse(raw);
      var minted = Date.parse(st && st.minted_at);
      if (!Number.isFinite(minted)) return true;
      var expires = Date.parse(st && st.expires_at);
      var ttlMs = Number.isFinite(expires) ? expires - minted : 12 * 3600 * 1000;
      if (ttlMs <= 0) return true;
      return Date.now() >= minted + ttlMs / 2;
    } catch (_e) {
      return true;
    }
  }

  function noteMintSuccess(expiresAt) {
    try {
      localStorage.setItem(
        MINT_STATE_KEY,
        JSON.stringify({
          minted_at: new Date().toISOString(),
          expires_at: expiresAt || "",
        }),
      );
    } catch (_e) {
      /* quota */
    }
  }

  async function refreshCapabilityIfOnline() {
    if (!navigator.onLine) return;
    if (!cfg().enabled) return;
    var mintUrl = cfg().offlineTokenMintUrl || cfg().offline_token_mint_url;
    if (!mintUrl) return;
    var deviceId = getDeviceId();
    if (!deviceId || deviceId.length < 8) return;
    if (!mintDue()) return;
    try {
      var res = await fetch(mintUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ device_id: deviceId }),
      });
      if (!res.ok) return;
      var data = await res.json();
      if (window.RMCIamSnapshot && window.RMCIamSnapshot.applyMintResponse) {
        window.RMCIamSnapshot.applyMintResponse(data);
      }
      noteMintSuccess(data && data.expires_at);
      if (data && data.capability_blob) {
        // The raw capability must never sit unsealed in storage. The vault
        // seal needs the user's PIN, which this bootstrap does not hold —
        // hand the blob to whichever PIN-holding surface is listening.
        try {
          window.dispatchEvent(
            new CustomEvent("rmc-offline-capability-minted", {
              detail: {
                capability_blob: data.capability_blob,
                expires_at: data.expires_at || "",
                permission_bitmap: data.permission_bitmap || [],
              },
            }),
          );
        } catch (_e2) {
          /* IE */
        }
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
