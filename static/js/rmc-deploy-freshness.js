/**
 * Post-deploy freshness guard.
 *
 * Compares the commit baked into this HTML shell against /-/version/ on the
 * live server. When they diverge, purge SW caches and reload so CSS/JS/template
 * fixes from the last deploy become visible without a manual hard-refresh.
 */
(function () {
  "use strict";

  var meta = document.querySelector('meta[name="rmc-deploy-sha"]');
  if (!meta) return;

  var pageSha = (meta.getAttribute("content") || "").trim().toLowerCase();
  if (!pageSha || pageSha === "unknown") return;

  var versionUrl = "/-/version/";
  var versionMeta = document.querySelector('meta[name="rmc-sw-cache-version"]');
  var pageSwVersion = versionMeta ? (versionMeta.getAttribute("content") || "").trim() : "";

  function normalizeSha(value) {
    return String(value || "").trim().toLowerCase();
  }

  function shaMatches(a, b) {
    if (!a || !b || a === "unknown" || b === "unknown") return true;
    if (a === b) return true;
    return a.slice(0, 12) === b.slice(0, 12) || a.slice(0, 7) === b.slice(0, 7);
  }

  function purgeSwCaches(registration) {
    if (!registration) return Promise.resolve();
    var targets = [];
    if (registration.active) targets.push(registration.active);
    if (registration.waiting) targets.push(registration.waiting);
    if (registration.installing) targets.push(registration.installing);
    targets.forEach(function (worker) {
      try {
        worker.postMessage({ type: "PURGE_ALL_CACHES" });
      } catch (_err) {}
    });
    return new Promise(function (resolve) {
      setTimeout(resolve, 120);
    });
  }

  function forceSwTakeover(registration) {
    if (!registration) return;
    try {
      registration.update();
    } catch (_err) {}
    if (registration.waiting) {
      try {
        registration.waiting.postMessage({ type: "SKIP_WAITING" });
      } catch (_err2) {}
    }
  }

  function reloadOnce(liveSha) {
    var key = "rmc-deploy-reload:" + liveSha;
    try {
      if (sessionStorage.getItem(key) === "1") return;
      sessionStorage.setItem(key, "1");
    } catch (_e) {}
    window.location.reload();
  }

  function checkFreshness() {
    fetch(versionUrl, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (payload) {
        if (!payload) return;
        var liveSha = normalizeSha(payload.commit_sha);
        if (shaMatches(pageSha, liveSha)) return;

        var reload = function () {
          reloadOnce(liveSha);
        };

        if (!("serviceWorker" in navigator)) {
          reload();
          return;
        }

        navigator.serviceWorker
          .getRegistration()
          .then(function (registration) {
            forceSwTakeover(registration);
            return purgeSwCaches(registration);
          })
          .then(reload)
          .catch(reload);
      })
      .catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", checkFreshness, { once: true });
  } else {
    checkFreshness();
  }
})();
