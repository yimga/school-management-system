/**
 * Optional LAN data-mule peer transfer (SODP batch 1412).
 * Uses signed NDJSON bundles — not CouchDB replication.
 */
(function (global) {
  "use strict";

  async function postBundle(peerBaseUrl, bundleBytes) {
    const url = (peerBaseUrl || "").replace(/\/$/, "") + "/api/v1/sync/bundle/upload/";
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/x-rmc-sync-bundle+ndjson" },
      body: bundleBytes,
    });
    return res.json();
  }

  global.RMCLanMuleSync = { postBundle };
})(typeof window !== "undefined" ? window : globalThis);
