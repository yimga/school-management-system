/**
 * RunMyCampus Dashboard Intelligence (v4.04.61) — per-user cockpit personalization.
 *
 * Progressive enhancement that attaches to the existing dashboard grid hook
 * `[data-rmc-tp-dashboard-cockpit]` (already on the backend / parent / teacher
 * landings) and personalizes the cockpit sections WITHOUT restructuring the
 * server-composed grid:
 *   - Customize: hide / show any section (by its data-rmc-collapsable-key)
 *   - Reorder: drag the grip on a top-level section (nested grid-blocks stay put)
 *   - Density: compact / comfortable / spacious for the whole grid
 *   - Adaptive Focus band: jump-links to sections that need attention (carry a
 *     count badge) + the ones this user opens most (localStorage usage)
 *
 * Preferences are SERVER-PERSISTED (durable + cross-device) into the EXISTING
 * DashboardUserPreference.dashboard_layout JSONField via a small endpoint — no
 * schema migration. A localStorage write-through cache applies instantly on load
 * (server is source of truth and reconciles). Config + the endpoint URL come from
 * the #rmc-dashboard-config island (SITE cascade, default-on). All in try/catch.
 */
(function () {
  "use strict";

  var LS_PREFS = "rmcDashPrefs:v1:";
  var LS_USAGE = "rmcDashUsage:v1:";
  var FREQUENT_MIN = 2;
  var FOCUS_MAX = 5;
  var DENSITIES = ["compact", "comfortable", "spacious"];

  var cfg = { intelligence: true, reorder: true, adaptive: true, density: "comfortable", prefsUrl: "" };

  function readConfig() {
    var node = document.getElementById("rmc-dashboard-config");
    if (!node || !node.textContent) { return; }
    try {
      var d = JSON.parse(node.textContent);
      ["intelligence", "reorder", "adaptive"].forEach(function (k) {
        if (d[k] === false || d[k] === 0 || d[k] === "0") { cfg[k] = false; }
      });
      if (typeof d.density === "string" && DENSITIES.indexOf(d.density) !== -1) { cfg.density = d.density; }
      if (typeof d.prefs_url === "string") { cfg.prefsUrl = d.prefs_url; }
    } catch (_) {}
  }

  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    if (m) { return m.getAttribute("content") || ""; }
    var i = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return i ? i.value : "";
  }

  function lsGet(key, fallback) {
    try { var r = localStorage.getItem(key); return r ? JSON.parse(r) : fallback; } catch (_) { return fallback; }
  }
  function lsSet(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (_) {} }

  function sectionKey(el) { return el.getAttribute("data-rmc-collapsable-key") || ""; }
  function sectionTitle(el) {
    var t = el.querySelector(".rmc-collapsable__title");
    return t ? (t.textContent || "").trim() : sectionKey(el);
  }
  function sectionMeta(el) {
    var m = el.querySelector(".rmc-collapsable__meta");
    return m ? (m.textContent || "").trim() : "";
  }

  function enhance(grid) {
    if (grid.dataset.rmcDashReady === "1") { return; }
    grid.dataset.rmcDashReady = "1";
    var surface = grid.getAttribute("data-rmc-tp-dashboard-cockpit") || "default";

    // All sections anywhere in the grid (for hide/show + focus); direct-child
    // sections only are reorderable (nested grid-blocks must stay as anchors).
    function allSections() { return Array.prototype.slice.call(grid.querySelectorAll(".rmc-collapsable[data-rmc-collapsable-key]")); }
    function directSections() {
      return Array.prototype.filter.call(grid.children, function (c) {
        return c.classList && c.classList.contains("rmc-collapsable") && c.hasAttribute("data-rmc-collapsable-key");
      });
    }

    var prefs = lsGet(LS_PREFS + surface, null) || {};
    var usage = lsGet(LS_USAGE + surface, {}) || {};

    function applyDensity(d) { grid.setAttribute("data-rmc-dash-density", DENSITIES.indexOf(d) !== -1 ? d : cfg.density); }
    function applyHidden(hidden) {
      var set = {}; (hidden || []).forEach(function (k) { set[k] = true; });
      allSections().forEach(function (s) { s.classList.toggle("rmc-dash-hidden", !!set[sectionKey(s)]); });
    }
    function applyOrder(order) {
      if (!order || !order.length) { return; }
      var direct = directSections();
      var byKey = {}; direct.forEach(function (s) { byKey[sectionKey(s)] = s; });
      // Re-append in saved order; unknown/new sections keep trailing.
      order.forEach(function (k) { if (byKey[k]) { grid.appendChild(byKey[k]); delete byKey[k]; } });
    }
    function apply(p) {
      if (!p) { applyDensity(cfg.density); return; }
      applyDensity(p.density || cfg.density);
      applyHidden(p.hidden);
      if (cfg.reorder) { applyOrder(p.order); }
    }

    apply(prefs); // instant from cache

    function currentPrefs() {
      return {
        density: grid.getAttribute("data-rmc-dash-density") || cfg.density,
        hidden: allSections().filter(function (s) { return s.classList.contains("rmc-dash-hidden"); }).map(sectionKey),
        order: directSections().map(sectionKey),
      };
    }
    function persist() {
      var p = currentPrefs();
      lsSet(LS_PREFS + surface, p);
      if (!cfg.prefsUrl) { return; }
      try {
        fetch(cfg.prefsUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
          body: JSON.stringify({ surface: surface, density: p.density, hidden: p.hidden, order: p.order }),
        });
      } catch (_) {}
    }

    // reconcile with the server (source of truth) after the instant cache apply
    if (cfg.prefsUrl) {
      try {
        fetch(cfg.prefsUrl + "?surface=" + encodeURIComponent(surface), { credentials: "same-origin", headers: { "Accept": "application/json" } })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            var sp = data && data.prefs;
            if (sp && (sp.order || sp.hidden || sp.density)) {
              apply(sp); lsSet(LS_PREFS + surface, currentPrefs()); rebuildFocus();
              syncCustomize();
            }
          })
          .catch(function () {});
      } catch (_) {}
    }

    /* ---- toolbar: Customize + density ---- */
    var bar = document.createElement("div");
    bar.className = "rmc-dash-bar";
    bar.setAttribute("role", "toolbar");

    var gear = document.createElement("button");
    gear.type = "button"; gear.className = "rmc-dash-btn"; gear.textContent = "⚙ Customize";
    gear.setAttribute("aria-expanded", "false");
    var panel = document.createElement("div");
    panel.className = "rmc-dash-cust";
    function syncCustomize() {
      panel.textContent = "";
      var h = document.createElement("div"); h.className = "rmc-dash-cust__head"; h.textContent = "Show / hide sections"; panel.appendChild(h);
      allSections().forEach(function (s) {
        var lab = document.createElement("label"); lab.className = "rmc-dash-cust__item";
        var cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = !s.classList.contains("rmc-dash-hidden");
        cb.addEventListener("change", function () { s.classList.toggle("rmc-dash-hidden", !cb.checked); persist(); rebuildFocus(); });
        lab.appendChild(cb); lab.appendChild(document.createTextNode(" " + sectionTitle(s)));
        panel.appendChild(lab);
      });
    }
    gear.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = panel.classList.toggle("is-open");
      gear.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) { syncCustomize(); }
    });
    document.addEventListener("click", function (ev) { if (!panel.contains(ev.target) && ev.target !== gear) { panel.classList.remove("is-open"); gear.setAttribute("aria-expanded", "false"); } });
    bar.appendChild(gear);

    var seg = document.createElement("div");
    seg.className = "rmc-dash-seg"; seg.setAttribute("role", "group"); seg.setAttribute("aria-label", "Dashboard density");
    [["compact", "Compact"], ["comfortable", "Cozy"], ["spacious", "Roomy"]].forEach(function (d) {
      var b = document.createElement("button"); b.type = "button"; b.className = "rmc-dash-seg__btn"; b.textContent = d[1];
      b.setAttribute("aria-pressed", (grid.getAttribute("data-rmc-dash-density") || cfg.density) === d[0] ? "true" : "false");
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(seg.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        applyDensity(d[0]); persist();
      });
      seg.appendChild(b);
    });
    bar.appendChild(seg);
    grid.insertBefore(bar, grid.firstChild);
    grid.insertBefore(panel, bar.nextSibling);

    /* ---- adaptive Focus band ---- */
    var focus = null;
    function rebuildFocus() {
      if (!cfg.adaptive) { return; }
      if (focus && focus.parentNode) { focus.parentNode.removeChild(focus); focus = null; }
      var entries = [];
      var seen = {};
      allSections().forEach(function (s) {
        if (s.classList.contains("rmc-dash-hidden")) { return; }
        var k = sectionKey(s), meta = sectionMeta(s);
        if (meta) { entries.push({ key: k, title: sectionTitle(s), meta: meta, attn: true }); seen[k] = true; }
      });
      Object.keys(usage).sort(function (a, b) { return usage[b] - usage[a]; }).forEach(function (k) {
        if (entries.length >= FOCUS_MAX || seen[k] || usage[k] < FREQUENT_MIN) { return; }
        var s = grid.querySelector('.rmc-collapsable[data-rmc-collapsable-key="' + (window.CSS && CSS.escape ? CSS.escape(k) : k) + '"]');
        if (s && !s.classList.contains("rmc-dash-hidden")) { entries.push({ key: k, title: sectionTitle(s), meta: "", attn: false }); seen[k] = true; }
      });
      if (!entries.length) { return; }
      focus = document.createElement("div"); focus.className = "rmc-dash-focus";
      var head = document.createElement("div"); head.className = "rmc-dash-focus__head"; head.textContent = "Focus"; focus.appendChild(head);
      var row = document.createElement("div"); row.className = "rmc-dash-focus__row";
      entries.slice(0, FOCUS_MAX).forEach(function (en) {
        var chip = document.createElement("button");
        chip.type = "button";
        chip.className = "rmc-dash-focus__chip" + (en.attn ? " is-attn" : "");
        chip.appendChild(document.createTextNode(en.title));
        if (en.meta) { var b = document.createElement("span"); b.className = "rmc-dash-focus__count"; b.textContent = en.meta; chip.appendChild(b); }
        chip.addEventListener("click", function () {
          var s = grid.querySelector('.rmc-collapsable[data-rmc-collapsable-key="' + (window.CSS && CSS.escape ? CSS.escape(en.key) : en.key) + '"]');
          if (s) { if (s.tagName === "DETAILS") { s.open = true; } try { s.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (_) {} }
        });
        row.appendChild(chip);
      });
      focus.appendChild(row);
      grid.insertBefore(focus, panel.nextSibling);
    }
    rebuildFocus();

    /* ---- reorder (direct-child sections only) ---- */
    if (cfg.reorder) {
      directSections().forEach(function (sec) {
        var head = sec.querySelector(".rmc-collapsable__head");
        if (!head || head.querySelector(".rmc-dash-grip")) { return; }
        var grip = document.createElement("span");
        grip.className = "rmc-dash-grip"; grip.textContent = "⠿"; grip.title = "Drag to reorder"; grip.setAttribute("draggable", "true"); grip.setAttribute("aria-hidden", "true");
        grip.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); });
        grip.addEventListener("dragstart", function (e) { sec.classList.add("rmc-dash-dragging"); try { e.dataTransfer.setData("text/plain", sectionKey(sec)); } catch (_) {} });
        grip.addEventListener("dragend", function () { sec.classList.remove("rmc-dash-dragging"); });
        sec.addEventListener("dragover", function (e) { if (grid.querySelector(".rmc-dash-dragging")) { e.preventDefault(); sec.classList.add("rmc-dash-dragover"); } });
        sec.addEventListener("dragleave", function () { sec.classList.remove("rmc-dash-dragover"); });
        sec.addEventListener("drop", function (e) {
          e.preventDefault(); sec.classList.remove("rmc-dash-dragover");
          var dragging = grid.querySelector(".rmc-dash-dragging");
          if (dragging && dragging !== sec) { grid.insertBefore(dragging, sec); persist(); }
        });
        head.insertBefore(grip, head.firstChild);
      });
    }

    /* ---- usage tracking: bump on expand ---- */
    allSections().forEach(function (s) {
      if (s.tagName !== "DETAILS") { return; }
      s.addEventListener("toggle", function () {
        if (!s.open) { return; }
        var k = sectionKey(s); usage[k] = (usage[k] || 0) + 1; lsSet(LS_USAGE + surface, usage);
      });
    });
  }

  function init() {
    readConfig();
    if (!cfg.intelligence) { return; }
    var grids = document.querySelectorAll("[data-rmc-tp-dashboard-cockpit]");
    Array.prototype.forEach.call(grids, function (g) { try { enhance(g); } catch (_) {} });
    window.RMCDashboardIntelligence = { enhance: enhance };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
