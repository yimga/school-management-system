/**
 * rmc-copilot-rail.js — Studio OS persistent AI presence (v3.53.1, 2026-05-21).
 *
 * Drives the right-side cockpit rail. Three sections hydrate on parse:
 *   1. Context strip   (server posture + mode badge update)
 *   2. Insights pulse  (3 rotating AI cards, refreshes every 90s OR on
 *                       custom event 'rmc:cockpit:context-changed')
 *   3. Quick actions   (4-6 role + surface filtered registry actions)
 *
 * Failure modes (graceful):
 *   - fetch error  -> existing server-rendered fallback stays in place;
 *                     posture pill flips to 'unavailable'
 *   - empty response -> rules-layer insights already populated server-side
 *   - JS load fails  -> static skeleton + server-rendered actions stay visible
 *
 * Armed-attribute invariant (mirrors rmc-reveal pattern from CLAUDE.md):
 *   the html[data-rmc-copilot-rail-armed] attribute is set synchronously at
 *   parse time. CSS that hides skeleton state ONLY removes itself once the
 *   attribute is present, so if this script fails to load the rail keeps
 *   its server-rendered shape instead of stranding a blank skeleton.
 *
 * Cloud-first AI direction:
 *   the rail never picks a backend. It calls /studio/copilot/rail/context/
 *   and renders whatever 'source' the server reports — cloud / rules / fallback.
 *   Ollama is edge-only; the rail just surfaces what the gateway decided.
 */
(function () {
  "use strict";

  if (typeof document === "undefined") { return; }

  /* Arm the rail synchronously at parse time. The CSS skeleton hide-rule keys
     off this attribute, so if rmc-copilot-rail.js never parses (CSP block,
     stale cache 404), the skeleton stays visible — never strands a blank rail. */
  try { document.documentElement.setAttribute("data-rmc-copilot-rail-armed", "1"); } catch (_e) {}

  var REFRESH_MS = 90000;
  var FETCH_TIMEOUT_MS = 8000;
  var refreshTimer = null;

  function rail() {
    return document.querySelector("[data-rmc-cockpit-region='rail']");
  }

  function endpoints() {
    var node = document.querySelector("[data-rmc-copilot-rail-endpoints]");
    if (!node) { return null; }
    return {
      contextUrl: node.getAttribute("data-context-url") || "",
      insightsUrl: node.getAttribute("data-insights-url") || "",
      currentMode: node.getAttribute("data-current-mode") || ""
    };
  }

  function fetchJson(url, signal) {
    return fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Accept": "application/json" },
      signal: signal
    }).then(function (r) {
      if (!r.ok) { throw new Error("rail-http-" + r.status); }
      return r.json();
    });
  }

  function withTimeout(url) {
    if (typeof AbortController === "undefined") {
      return fetchJson(url, undefined);
    }
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, FETCH_TIMEOUT_MS);
    return fetchJson(url, controller.signal).then(
      function (v) { clearTimeout(timer); return v; },
      function (e) { clearTimeout(timer); throw e; }
    );
  }

  function renderPosture(snapshot) {
    if (!snapshot) { return; }
    var posture = snapshot.posture_mode || "unknown";
    var pill = document.querySelector("[data-rmc-copilot-rail-posture]");
    if (!pill) { return; }
    pill.setAttribute("data-state", posture);
    var label = pill.querySelector("[data-rmc-copilot-rail-posture-label]");
    if (label) {
      if (posture === "live_cloud") { label.textContent = "Live · cloud AI"; }
      else if (posture === "live_local") { label.textContent = "Live · local AI"; }
      else if (posture === "guided") { label.textContent = "Guided mode"; }
      else if (posture === "unavailable") { label.textContent = "AI unavailable"; }
      else { label.textContent = "Checking..."; }
    }
    var modeNode = document.querySelector("[data-rmc-copilot-rail-mode]");
    if (modeNode && snapshot.mode) {
      modeNode.textContent = snapshot.mode.charAt(0).toUpperCase() + snapshot.mode.slice(1);
    }
  }

  function renderSourceBadge(insights) {
    var badge = document.querySelector("[data-rmc-copilot-rail-insights-source]");
    if (!badge) { return; }
    if (!insights || !insights.length) { badge.textContent = ""; return; }
    var firstSource = insights[0].source || "";
    if (firstSource === "cloud") {
      badge.textContent = "· cloud";
      badge.setAttribute("data-source", "cloud");
    } else if (firstSource === "rules") {
      badge.textContent = "· guided";
      badge.setAttribute("data-source", "rules");
    } else {
      badge.textContent = "";
      badge.setAttribute("data-source", "fallback");
    }
  }

  function renderInsights(insights) {
    var list = document.querySelector("[data-rmc-copilot-rail-insights-list]");
    if (!list) { return; }
    list.innerHTML = "";
    if (!insights || !insights.length) {
      var empty = document.createElement("li");
      empty.className = "rmc-copilot-rail__insight rmc-copilot-rail__insight--empty";
      empty.textContent = "No insights right now.";
      list.appendChild(empty);
      return;
    }
    for (var i = 0; i < insights.length; i++) {
      var item = insights[i];
      var li = document.createElement("li");
      li.className = "rmc-copilot-rail__insight";
      li.setAttribute("data-source", item.source || "");
      var title = document.createElement("div");
      title.className = "rmc-copilot-rail__insight-title";
      title.textContent = item.title || "";
      var body = document.createElement("div");
      body.className = "rmc-copilot-rail__insight-body";
      body.textContent = item.body || "";
      li.appendChild(title);
      li.appendChild(body);
      list.appendChild(li);
    }
    renderSourceBadge(insights);
  }

  function renderQuickActions(actions) {
    var list = document.querySelector("[data-rmc-copilot-rail-actions-list]");
    if (!list) { return; }
    if (!actions || !actions.length) {
      /* Keep the server-rendered fallback in place when registry returns 0 — do nothing. */
      return;
    }
    list.innerHTML = "";
    for (var i = 0; i < actions.length; i++) {
      var a = actions[i];
      if (!a || !a.url) { continue; }
      var li = document.createElement("li");
      var anchor = document.createElement("a");
      anchor.className = "rmc-cockpit__rail-action";
      anchor.href = a.url;
      anchor.setAttribute("data-kind", a.kind || "");
      var icon = document.createElement("span");
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = a.icon || "›";
      var label = document.createElement("span");
      label.textContent = a.label || "";
      anchor.appendChild(icon);
      anchor.appendChild(label);
      li.appendChild(anchor);
      list.appendChild(li);
    }
  }

  /* Governance registries (Feature-Gap + Backlog) — operator-only, server-gated.
     Hidden section stays hidden when the payload omits `registry` (non-staff /
     disabled / unreadable), so nothing leaks to tenant users. */
  function renderRegistry(registry) {
    var section = document.querySelector("[data-rmc-copilot-rail-registry]");
    var list = document.querySelector("[data-rmc-copilot-rail-registry-list]");
    if (!section || !list) { return; }
    list.innerHTML = "";
    if (!registry || !registry.length) {
      section.setAttribute("hidden", "hidden");
      return;
    }
    for (var i = 0; i < registry.length; i++) {
      var item = registry[i];
      if (!item) { continue; }
      var li = document.createElement("li");
      li.className = "rmc-copilot-rail__insight";
      li.setAttribute("data-source", "registry");
      var title = document.createElement("div");
      title.className = "rmc-copilot-rail__insight-title";
      if (item.url) {
        var anchor = document.createElement("a");
        anchor.href = item.url;
        anchor.textContent = item.title || "";
        title.appendChild(anchor);
      } else {
        title.textContent = item.title || "";
      }
      var body = document.createElement("div");
      body.className = "rmc-copilot-rail__insight-body";
      body.textContent = item.body || "";
      li.appendChild(title);
      li.appendChild(body);
      list.appendChild(li);
    }
    section.removeAttribute("hidden");
  }

  function markUnavailable() {
    var pill = document.querySelector("[data-rmc-copilot-rail-posture]");
    if (pill) {
      pill.setAttribute("data-state", "unavailable");
      var label = pill.querySelector("[data-rmc-copilot-rail-posture-label]");
      if (label) { label.textContent = "AI unavailable"; }
    }
    /* Leave server-rendered fallback actions / skeleton in place. */
  }

  function loadContext() {
    var ep = endpoints();
    if (!ep || !ep.contextUrl) { markUnavailable(); return; }
    var url = ep.contextUrl;
    if (ep.currentMode) {
      url += (url.indexOf("?") === -1 ? "?" : "&") + "mode=" + encodeURIComponent(ep.currentMode);
    }
    withTimeout(url).then(function (data) {
      if (!data) { markUnavailable(); return; }
      if (data.snapshot) { renderPosture(data.snapshot); }
      if (data.insights) { renderInsights(data.insights); }
      if (data.quick_actions) { renderQuickActions(data.quick_actions); }
      renderRegistry(data.registry);
    }).catch(function () {
      markUnavailable();
    });
  }

  function refreshInsights() {
    var ep = endpoints();
    if (!ep || !ep.insightsUrl) { return; }
    var url = ep.insightsUrl;
    if (ep.currentMode) {
      url += (url.indexOf("?") === -1 ? "?" : "&") + "mode=" + encodeURIComponent(ep.currentMode);
    }
    withTimeout(url).then(function (data) {
      if (!data) { return; }
      if (data.insights) { renderInsights(data.insights); }
      if (data.posture_mode) {
        renderPosture({ posture_mode: data.posture_mode });
      }
    }).catch(function () { /* silent — keep existing insights */ });
  }

  function startInterval() {
    if (refreshTimer) { return; }
    refreshTimer = setInterval(function () {
      if (!document.hidden) { refreshInsights(); }
    }, REFRESH_MS);
  }

  function stopInterval() {
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  }

  function init() {
    if (!rail()) { return; }
    loadContext();
    startInterval();
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { stopInterval(); }
      else { startInterval(); refreshInsights(); }
    });
    document.addEventListener("rmc:cockpit:context-changed", function () {
      loadContext();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
