/**
 * Optional LAN data-mule peer transfer (SODP batch 1412 / depth 1413).
 * Uses signed NDJSON bundles — not CouchDB replication.
 */
(function (global) {
  "use strict";

  function hubFromConfig() {
    var cfg = global.SMS_OFFLINE_CONFIG || {};
    return (cfg.hubBaseUrl || "").trim().replace(/\/$/, "");
  }

  async function postBundle(peerBaseUrl, bundleBytes) {
    const uploadPath =
      (typeof window !== "undefined" &&
        window.RMCPlatformSurface &&
        window.RMCPlatformSurface.url("sync_bundle_upload")) ||
      "";
    if (!uploadPath) return;
    const url = (peerBaseUrl || "").replace(/\/$/, "") + uploadPath;
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/x-rmc-sync-bundle+ndjson" },
      body: bundleBytes,
    });
    return res.json();
  }

  function noteHubOnline(hubUrl) {
    try {
      global.dispatchEvent(
        new CustomEvent("rmc-hub-online", { detail: { hubBaseUrl: hubUrl || hubFromConfig() } }),
      );
    } catch (_e) {
      /* ignore */
    }
  }

  async function tryHubHealth(hubUrl) {
    var base = (hubUrl || hubFromConfig()).replace(/\/$/, "");
    if (!base) return false;
    try {
      var res = await fetch(base + "/health/", { method: "GET", cache: "no-store" });
      return res.ok;
    } catch (_e) {
      return false;
    }
  }

  global.RMCLanMuleSync = {
    postBundle,
    hubFromConfig,
    noteHubOnline,
    tryHubHealth,
  };
})(typeof window !== "undefined" ? window : globalThis);
