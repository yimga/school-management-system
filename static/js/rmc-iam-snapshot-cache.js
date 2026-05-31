/**
 * Read-only IAM permission snapshot cache (batch 1507 follow-up).
 * Stores signed server snapshot in localStorage for offline navigation gating.
 */
(function (global) {
  "use strict";

  var STORAGE_PREFIX = "rmc_iam_snapshot_v1_";
  var cfg = function () {
    return global.SMS_OFFLINE_CONFIG || {};
  };

  function schoolKey() {
    var sk =
      (global.document &&
        global.document.documentElement &&
        global.document.documentElement.getAttribute("data-school-id")) ||
      "";
    if (sk) return String(sk);
    try {
      var raw = global.localStorage.getItem("rmc_active_school_id");
      if (raw) return String(raw);
    } catch (_e) {
      /* ignore */
    }
    return "default";
  }

  function storageKey() {
    return STORAGE_PREFIX + schoolKey();
  }

  function parseExpires(iso) {
    if (!iso) return 0;
    var t = Date.parse(iso);
    return Number.isFinite(t) ? t : 0;
  }

  function isExpired(snap) {
    if (!snap || !snap.expires_at) return true;
    return Date.now() >= parseExpires(snap.expires_at);
  }

  function load() {
    try {
      var raw = global.localStorage.getItem(storageKey());
      if (!raw) return null;
      var snap = JSON.parse(raw);
      if (!snap || typeof snap !== "object") return null;
      if (isExpired(snap)) {
        global.localStorage.removeItem(storageKey());
        return null;
      }
      return snap;
    } catch (_e) {
      return null;
    }
  }

  function save(snap) {
    if (!snap || typeof snap !== "object") return;
    try {
      global.localStorage.setItem(storageKey(), JSON.stringify(snap));
    } catch (_e) {
      /* quota */
    }
  }

  function snapshotUrl() {
    var c = cfg();
    var u = (c.permissionSnapshotUrl || c.permission_snapshot_url || "").trim();
    if (u) return u;
    if (global.RMCPlatformSurface && global.RMCPlatformSurface.url) {
      return global.RMCPlatformSurface.url("permission_snapshot");
    }
    return "";
  }

  function fetchSnapshot() {
    if (!global.navigator.onLine) {
      return Promise.resolve(load());
    }
    var url = snapshotUrl();
    var sep = url.indexOf("?") >= 0 ? "&" : "?";
    var deviceId = "";
    try {
      deviceId = global.localStorage.getItem("rmc_offline_device_id") || "";
    } catch (_e) {
      deviceId = "";
    }
    if (deviceId) {
      url += sep + "device_id=" + encodeURIComponent(deviceId.slice(0, 128));
    }
    return fetch(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("snapshot_http_" + res.status);
        return res.json();
      })
      .then(function (data) {
        var snap = (data && data.snapshot) || data;
        if (!snap) return load();
        save(snap);
        try {
          global.dispatchEvent(
            new CustomEvent("rmc-iam-snapshot-updated", { detail: { snapshot: snap } }),
          );
        } catch (_e2) {
          /* IE */
        }
        return snap;
      })
      .catch(function () {
        return load();
      });
  }

  function hasCapability(code) {
    var snap = load();
    if (!snap) return false;
    var caps = snap.capabilities || [];
    return caps.indexOf(code) >= 0;
  }

  function refresh() {
    return fetchSnapshot();
  }

  function applyMintResponse(mintJson) {
    if (!mintJson || !mintJson.iam_snapshot) return load();
    save(mintJson.iam_snapshot);
    return mintJson.iam_snapshot;
  }

  global.RMCIamSnapshot = {
    load: load,
    save: save,
    refresh: refresh,
    fetchSnapshot: fetchSnapshot,
    hasCapability: hasCapability,
    applyMintResponse: applyMintResponse,
    isExpired: isExpired,
  };

  function boot() {
    if (!cfg().enabled) return;
    refresh();
    global.addEventListener("online", function () {
      refresh();
    });
  }

  if (global.document && global.document.readyState === "loading") {
    global.document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(typeof window !== "undefined" ? window : this);
