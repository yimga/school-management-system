/**
 * Global edge ↔ cloud sync progress bar (all tenant pages on box deployments).
 * Polls school-scoped JSON; paints percent to 100% when phase is ok/running.
 */
(function () {
  "use strict";

  var POLL_FLOOR_MS = 2000;
  var HIDE_WHEN_IDLE_OK_MS = 8000;

  function bar() {
    return document.querySelector("[data-rmc-edge-sync-bar]");
  }

  function parsePercent(value) {
    var raw = String(value == null ? "0" : value).replace("%", "").trim();
    var n = Number(raw);
    return isFinite(n) ? Math.max(0, Math.min(100, n)) : 0;
  }

  function formatPercent(n) {
    return n.toFixed(2);
  }

  function setVisible(el, show) {
    if (!el) return;
    el.classList.toggle("d-none", !show);
  }

  function applyPayload(payload) {
    var host = bar();
    if (!host || !payload || payload.ok === false) return;
    var phase = payload.phase || "idle";
    var pct = parsePercent(payload.percent_complete);
    var fill = host.querySelector("[data-rmc-edge-sync-fill]");
    var pctEl = host.querySelector("[data-rmc-edge-sync-pct]");
    var headlineEl = host.querySelector("[data-rmc-edge-sync-headline]");
    var pctStr = formatPercent(pct);

    host.setAttribute("data-phase", phase);
    host.setAttribute("data-percent", pctStr);
    if (fill) {
      fill.style.width = pctStr + "%";
      fill.setAttribute("aria-valuenow", pctStr);
      fill.classList.toggle("progress-bar-animated", phase === "running");
      fill.classList.toggle("progress-bar-striped", phase === "running");
    }
    if (pctEl) pctEl.textContent = pctStr + "%";
    if (headlineEl && payload.headline) headlineEl.textContent = payload.headline;

    var show =
      phase === "running" ||
      phase === "queued" ||
      phase === "failed" ||
      (phase === "ok" && pct < 100) ||
      (phase === "idle" && pct < 100);
    if (phase === "ok" && pct >= 100) {
      show = true;
      window.setTimeout(function () {
        setVisible(host, false);
      }, HIDE_WHEN_IDLE_OK_MS);
    }
    setVisible(host, show);
    document.dispatchEvent(
      new CustomEvent("rmc:edge-sync-status", { detail: payload })
    );
  }

  function poll() {
    var host = bar();
    if (!host) return;
    var url = host.getAttribute("data-status-url");
    if (!url || typeof window.fetch !== "function") return;
    window
      .fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (resp) {
        return resp.ok ? resp.json() : null;
      })
      .then(function (payload) {
        if (payload) applyPayload(payload);
      })
      .catch(function () {
        /* next tick retries */
      });
  }

  function onOnline() {
    poll();
    document.dispatchEvent(new CustomEvent("rmc:edge-sync-poll"));
  }

  function start() {
    var host = bar();
    if (!host) return;
    poll();
    var ms = Number(host.getAttribute("data-poll-ms") || 3000);
    if (!isFinite(ms) || ms < POLL_FLOOR_MS) ms = 3000;
    window.setInterval(poll, ms);
    window.addEventListener("online", onOnline);
    document.addEventListener("rmc:edge-sync-poll", poll);
    document.addEventListener("rmc:sync-center-status", function (ev) {
      applyPayload(ev.detail || {});
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
