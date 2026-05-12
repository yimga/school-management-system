/**
 * AI Copilot health pill — surfaces the /api/ai/health/ status inside the
 * floating copilot panel so users see degraded mode rather than silent failures.
 *
 * Markup contract (set in templates/components/ai_copilot.html):
 *   <span id="aiCopilotStatus" data-state="unknown">
 *     <span class="ai-status-dot"></span>
 *     <span class="ai-status-text">…</span>
 *   </span>
 *
 * URL is read from the page-data-components__ai_copilot-1 JSON island.
 */
(function () {
  "use strict";

  function readEndpoint() {
    var island = document.getElementById("page-data-components__ai_copilot-1");
    if (!island || !island.textContent) { return null; }
    try {
      var data = JSON.parse(island.textContent);
      return data.ai_health_url || null;
    } catch (_) {
      return null;
    }
  }

  function applyState(state, text) {
    var pill = document.getElementById("aiCopilotStatus");
    if (pill) {
      pill.setAttribute("data-state", state);
      var textNode = pill.querySelector(".ai-status-text");
      if (textNode) { textNode.textContent = text; }
    }
    /* Improvement A (2026-05-12): mirror the state onto the avatar micro-dot
       so degraded mode is visible at-a-glance in every shell, not only when
       the copilot panel is open. */
    var pulses = document.querySelectorAll("[data-rmc-user-ai-pulse]");
    pulses.forEach(function (n) { n.setAttribute("data-state", state); });
  }

  function describe(payload) {
    if (!payload) { return ["error", "Offline"]; }
    if (payload.reachable && payload.provider === "ollama") {
      var latency = payload.latency_ms != null ? " · " + payload.latency_ms + "ms" : "";
      return ["ok", "Online" + latency];
    }
    if (payload.fallback_active) {
      return ["degraded", "Limited mode"];
    }
    if (payload.rules_fallback_enabled) {
      return ["degraded", "Limited mode"];
    }
    return ["error", "Offline"];
  }

  function probe() {
    var url = readEndpoint();
    if (!url) { applyState("unknown", "Unavailable"); return; }
    fetch(url, { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (json) {
        var pair = describe(json);
        applyState(pair[0], pair[1]);
      })
      .catch(function () { applyState("error", "Offline"); });
  }

  function init() {
    /* Probe once on load; re-probe when the copilot is opened. */
    probe();
    var trigger = document.getElementById("aiCopilotTrigger");
    if (trigger) { trigger.addEventListener("click", function () { setTimeout(probe, 200); }); }
    /* Light periodic refresh — every 90s, only while the page is visible. */
    var interval = null;
    function startInterval() {
      if (interval) { return; }
      interval = setInterval(function () {
        if (!document.hidden) { probe(); }
      }, 90000);
    }
    function stopInterval() {
      if (interval) { clearInterval(interval); interval = null; }
    }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { stopInterval(); } else { startInterval(); probe(); }
    });
    startInterval();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
