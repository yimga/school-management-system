/**
 * Minimal RUM: one beacon on tab hide (visibilitychange) with LCP if available.
 * Requires window.__RUM__ = { u: absolute ingest URL, k: token } from template.
 */
(function () {
  var cfg = window.__RUM__;
  if (!cfg || !cfg.u || !cfg.k) return;

  var sent = false;

  function buildMetrics() {
    var m = {};
    try {
      if (performance && performance.getEntriesByType) {
        var lcp = performance.getEntriesByType("largest-contentful-paint");
        if (lcp && lcp.length) {
          m.lcp = lcp[lcp.length - 1].startTime;
        }
      }
      if (performance && performance.timing) {
        var t = performance.timing;
        if (t.loadEventEnd > 0 && t.navigationStart > 0) {
          m.nav = t.loadEventEnd - t.navigationStart;
        }
      }
    } catch (e) { /* ignore */ }
    return m;
  }

  function send() {
    if (sent) return;
    sent = true;
    var payload = {
      token: cfg.k,
      path: (window.location && window.location.pathname) ? window.location.pathname : "",
      navigation_type: (performance && performance.navigation && performance.navigation.type !== undefined)
        ? String(performance.navigation.type)
        : "",
      metrics: buildMetrics()
    };
    var body = JSON.stringify(payload);
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: "application/json" });
        navigator.sendBeacon(cfg.u, blob);
      } else {
        fetch(cfg.u, {
          method: "POST",
          body: body,
          headers: { "Content-Type": "application/json" },
          keepalive: true,
          credentials: "omit"
        }).catch(function () {});
      }
    } catch (e) { /* ignore */ }
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      send();
    }
  });
  window.addEventListener("pagehide", send);
})();
