/**
 * Post-deploy freshness guard.
 *
 * Compares the commit baked into this HTML shell against /-/version/ on the live
 * server. Two cases, deliberately handled differently:
 *
 *   1. ON ARRIVAL — if the server is already ahead of the HTML you just loaded,
 *      silently purge SW caches and reload to the fresh version. You haven't
 *      interacted yet, so there's nothing to interrupt.
 *
 *   2. MID-SESSION — if a deploy lands WHILE you're on the page, do NOT yank it
 *      out from under in-progress work. Surface a dismissible "new version
 *      available — Refresh" toast and let you reload when ready.
 */
(function () {
  "use strict";

  function normalizeSha(value) {
    return String(value || "").trim().toLowerCase();
  }

  var meta = document.querySelector('meta[name="rmc-deploy-sha"]');
  if (!meta) return;

  var pageSha = normalizeSha(meta.getAttribute("content"));
  if (!pageSha || pageSha === "unknown") return;

  var VERSION_URL = "/-/version/";
  // Re-check cadence for a deploy that lands while the user is on the page.
  var POLL_INTERVAL_MS = 3 * 60 * 1000;
  var pollTimer = null;
  var toastShown = false;

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

  // Purge the stale SW caches, then reload to the just-deployed version.
  function freshenAndReload(liveSha) {
    if (!("serviceWorker" in navigator)) {
      reloadOnce(liveSha);
      return;
    }
    navigator.serviceWorker
      .getRegistration()
      .then(function (registration) {
        forceSwTakeover(registration);
        return purgeSwCaches(registration);
      })
      .then(function () {
        reloadOnce(liveSha);
      })
      .catch(function () {
        reloadOnce(liveSha);
      });
  }

  // Non-disruptive prompt for a deploy that landed mid-session. Built with DOM
  // APIs + textContent (no innerHTML) so nothing dynamic is ever interpolated as
  // markup; styled via .rmc-deploy-toast in rmc-class-grammar.css (token-only).
  function showUpdateToast(liveSha) {
    if (toastShown || !document.body) return;
    toastShown = true;
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }

    var toast = document.createElement("div");
    toast.className = "rmc-deploy-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");

    var msg = document.createElement("span");
    msg.className = "rmc-deploy-toast__msg";
    msg.textContent = "A new version is available.";
    toast.appendChild(msg);

    var refresh = document.createElement("button");
    refresh.type = "button";
    refresh.className = "rmc-deploy-toast__refresh";
    refresh.textContent = "Refresh";
    refresh.addEventListener("click", function () {
      refresh.disabled = true;
      freshenAndReload(liveSha);
    });
    toast.appendChild(refresh);

    var dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "rmc-deploy-toast__dismiss";
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "×";
    dismiss.addEventListener("click", function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    });
    toast.appendChild(dismiss);

    document.body.appendChild(toast);
  }

  function check(onStale) {
    fetch(VERSION_URL, {
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
        onStale(liveSha);
      })
      .catch(function () {});
  }

  function start() {
    // Case 1 — on arrival: silently freshen if the server is already ahead.
    check(freshenAndReload);
    // Case 2 — mid-session: poll (only while the tab is visible) and prompt with
    // a toast instead of reloading under the user's feet.
    pollTimer = window.setInterval(function () {
      if (document.visibilityState === "visible") {
        check(showUpdateToast);
      }
    }, POLL_INTERVAL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
