/**
 * R2 - After offline queue flush, rehydrate live UI from server state (no manual refresh).
 * Listens for service-worker sync-complete + sms-sync-end, runs mirror hydration, then
 * triggers HTMX `rmc-reconnect` on body and `rmc:reconnect-rehydrate` for health widgets.
 */
(function (global) {
  "use strict";

  var DEBOUNCE_MS = 350;
  var timer = null;

  function afterHydration(cb) {
    if (global.SMSSyncManager && typeof global.SMSSyncManager.hydrateAfterSync === "function") {
      global.SMSSyncManager.hydrateAfterSync().finally(cb);
      return;
    }
    cb();
  }

  function rehydrateViewport() {
    if (global.htmx && typeof global.htmx.trigger === "function") {
      global.htmx.trigger(global.document.body, "rmc-reconnect");
    }
    global.document.dispatchEvent(new CustomEvent("rmc:reconnect-rehydrate"));

    global.document.querySelectorAll("[data-rmc-reconnect-rehydrate]").forEach(function (el) {
      var url = el.getAttribute("data-rmc-reconnect-url") || el.getAttribute("hx-get");
      if (!url) return;
      var mode = (el.getAttribute("data-rmc-reconnect-rehydrate") || "fetch").toLowerCase();
      if (mode === "htmx" && global.htmx) {
        global.htmx.ajax("GET", url, { target: el, swap: "outerHTML" });
        return;
      }
      fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "text/html" },
      })
        .then(function (r) {
          if (!r.ok) throw new Error("rehydrate_" + r.status);
          return r.text();
        })
        .then(function (html) {
          if (html) el.outerHTML = html;
        })
        .catch(function () {});
    });
  }

  function scheduleRehydrate() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () {
      timer = null;
      afterHydration(rehydrateViewport);
    }, DEBOUNCE_MS);
  }

  function init() {
    if (global.navigator.serviceWorker) {
      global.navigator.serviceWorker.addEventListener("message", function (event) {
        var data = event.data;
        if (data && data.type === "sync-complete") scheduleRehydrate();
      });
    }
    global.document.addEventListener("sms-sync-end", scheduleRehydrate);
  }

  if (global.document.readyState === "loading") {
    global.document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  global.RMCReconnectRehydrate = { schedule: scheduleRehydrate };
})(typeof window !== "undefined" ? window : this);
