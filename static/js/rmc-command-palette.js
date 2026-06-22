/**
 * RunMyCampus Command Palette (⌘K / Ctrl+K) — the single command ENGINE.
 *
 * v4.04.59 (2026-06-22): unified-engine wave. This palette is now the one
 * surface bound to ⌘K platform-wide. It federates four sources into one
 * ranked, fuzzy-searchable, CSP-safe list:
 *
 *   1. static groups from the #rmc-cmdk-data island (incl. page-aware +
 *      slash + AI injections, which mutate that island BEFORE we read it);
 *   2. the server action REGISTRY (/api/command-bar/actions/, role + tenant
 *      filtered) — previously owned by the separate rmc-command-bar.js, now
 *      absorbed so there is no duplicate ⌘K listener;
 *   3. the rendered SIDEBAR nav (harvested from the [data-sidebar-nav] DOM —
 *      zero-backend, the ~30-40% of nav targets the palette used to miss);
 *   4. live remote topology + AI results (unchanged).
 *
 * Intelligence: fuzzy subsequence matching with <mark> highlight (built with
 * createElement + textContent, never innerHTML of runtime data), an adaptive
 * Pinned / Frequent / Recent surface (localStorage usage model), and per-user
 * pinning. Everything degrades to the server-rendered list inside try/catch.
 *
 * rmc-command-bar.js detects this engine (#rmc-cmdk) and yields its keybinding.
 */
(function () {
  "use strict";

  var ROOT_ID = "rmc-cmdk";
  var INPUT_ID = "rmc-cmdk-input";
  var LIST_ID = "rmc-cmdk-list";
  var DATA_ID = "rmc-cmdk-data";
  var RECENT_KEY = "rmc-cmdk:recent";
  var USAGE_KEY = "rmc-cmdk:usage";
  var PINNED_KEY = "rmc-cmdk:pinned";
  var RECENT_MAX = 6;
  var FREQUENT_MAX = 5;
  var FREQUENT_MIN_HITS = 2;
  var RESULTS_MAX = 40;

  var config = { groups: [], api_url: "", ai_center_url: "", actions_url: "" };
  // Engine capability flags — read from the #rmc-cmdk root data-attrs, which
  // the template emits from the SITE cascade (default-on, operator-overridable).
  var cfg = { enabled: true, fuzzy: true, adaptive: true, federateSidebar: true };
  var state = {
    open: false,
    query: "",
    staticItems: [],
    registryItems: [],
    sidebarItems: [],
    remoteItems: [],
    filtered: [],     // flat, navigable (no band headers)
    activeIndex: 0,
    remoteTimer: null,
    remoteFetchId: 0,
  };

  function readData() {
    var node = document.getElementById(DATA_ID);
    if (!node || !node.textContent) { return { groups: [] }; }
    try { return JSON.parse(node.textContent); } catch (_) { return { groups: [] }; }
  }

  function readFlags() {
    var root = document.getElementById(ROOT_ID);
    if (!root) { return; }
    function on(name, dflt) {
      var v = root.getAttribute(name);
      if (v === null || v === "") { return dflt; }
      return v !== "0" && v !== "false";
    }
    cfg.enabled = on("data-rmc-cmdk-enabled", true);
    cfg.fuzzy = on("data-rmc-cmdk-fuzzy", true);
    cfg.adaptive = on("data-rmc-cmdk-adaptive", true);
    cfg.federateSidebar = on("data-rmc-cmdk-federate-sidebar", true);
  }

  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }

  /* ---- localStorage: recent / usage-frequency / pinned ---- */

  function readJson(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) { return fallback; }
  }
  function writeJson(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (_) {}
  }

  function readRecent() { return readJson(RECENT_KEY, []) || []; }
  function pushRecent(item) {
    if (!item || !item.url || item.locked) { return; }
    var recent = readRecent().filter(function (r) { return r.url !== item.url; });
    recent.unshift({ label: item.label, url: item.url, icon: item.icon });
    writeJson(RECENT_KEY, recent.slice(0, RECENT_MAX));
  }
  function recentItems() {
    return readRecent().map(function (r) {
      return { label: r.label, url: r.url, icon: r.icon, group: "Recent", source: "recent", keywords: "recent " + (r.label || ""), locked: false };
    });
  }

  function readUsage() { return readJson(USAGE_KEY, {}) || {}; }
  function bumpUsage(item) {
    if (!item || !item.url) { return; }
    var usage = readUsage();
    usage[item.url] = (usage[item.url] || 0) + 1;
    writeJson(USAGE_KEY, usage);
  }

  function readPinned() { return readJson(PINNED_KEY, []) || []; }
  function isPinned(url) { return !!url && readPinned().indexOf(url) !== -1; }
  function togglePin(url) {
    if (!url) { return; }
    var pinned = readPinned();
    var i = pinned.indexOf(url);
    if (i === -1) { pinned.push(url); } else { pinned.splice(i, 1); }
    writeJson(PINNED_KEY, pinned);
  }

  /* ---- source federation ---- */

  function sourceForGroup(groupLabel, item, groupTag) {
    if (item && item.action && /ask-ai|open-ai/.test(item.action)) { return "ai"; }
    var g = (groupLabel || "").toLowerCase();
    if (/\bai\b/.test(g)) { return "ai"; }
    if (groupTag === "page" || groupTag === "slash" || /action/.test(g)) { return "action"; }
    return "nav";
  }

  function flattenItems(groups) {
    var items = [];
    (groups || []).forEach(function (g) {
      var groupTag = g["data-rmc-cmdk-group"] || "";
      (g.items || []).forEach(function (it) {
        if (!it || (!it.url && !it.action)) { return; }
        items.push({
          label: it.label || "",
          url: it.url || null,
          action: it.action || null,
          icon: it.icon || "bi-arrow-right-circle",
          keywords: (it.keywords || "") + " " + (g.label || ""),
          group: g.label || "",
          source: sourceForGroup(g.label, it, groupTag),
          locked: false,
        });
      });
    });
    return items;
  }

  // Map a registry kind → a friendlier group label + federation source.
  var KIND_LABELS = {
    navigate: "Navigate", settings: "Settings", palette: "Palette",
    install: "Install", deploy: "Deploy", health: "Operations",
  };
  function mapRegistry(actions) {
    return (actions || []).map(function (a) {
      var kind = a.kind || "navigate";
      return {
        label: a.label || "",
        url: a.url || null,
        action: null,
        icon: a.icon || "›",
        keywords: (a.label || "") + " " + kind,
        group: KIND_LABELS[kind] || "Actions",
        source: kind === "navigate" ? "nav" : "action",
        locked: false,
        destructive: !!a.destructive,
      };
    });
  }

  // Harvest the rendered sidebar nav as a federated source. Zero-backend and
  // CSP-safe — we only read href + visible text the user can already see.
  function harvestSidebar() {
    var out = [];
    var seen = {};
    var anchors = document.querySelectorAll('[data-sidebar-nav] a[href]');
    Array.prototype.forEach.call(anchors, function (a) {
      var href = a.getAttribute("href") || "";
      if (!href || href.charAt(0) === "#" || /^(javascript:|mailto:|tel:)/i.test(href)) { return; }
      if (seen[href]) { return; }
      var label = (a.textContent || "").replace(/\s+/g, " ").trim();
      if (!label || label.length > 60) { return; }
      seen[href] = true;
      out.push({
        label: label, url: href, action: null, icon: "bi-signpost",
        keywords: label + " sidebar", group: "Sidebar", source: "sidebar", locked: false,
      });
    });
    return out;
  }

  function mapRemote(row) {
    var isEscalate = row.type === "escalate";
    return {
      label: row.label || "",
      path_label: row.path_label || "",
      detail: row.detail || "",
      url: row.url || (isEscalate && config.help_center_url ? config.help_center_url : null),
      action: row.ask_ai_center ? "rmc:cmdk:ask-ai" : null,
      icon: row.icon || "bi-arrow-right-circle",
      keywords: (row.label || "") + " " + (row.path_label || ""),
      group: isEscalate ? "Support" : row.type === "documentation" ? "How-to" : row.type === "locked" ? "Restricted" : "Topology",
      source: row.ask_ai_center ? "ai" : "nav",
      locked: row.type === "locked" || !!row.locked,
      missing_permission: row.missing_permission || "",
    };
  }

  function askAiItem(query) {
    return {
      label: 'Ask AI: "' + query + '"',
      url: null,
      action: "rmc:cmdk:ask-ai",
      icon: "bi-stars",
      keywords: "ask ai engine room " + query,
      group: "AI",
      source: "ai",
      locked: false,
    };
  }

  /* ---- fuzzy match + scoring ---- */

  // Returns {score, hits:[label char indexes]} or {score:0} for no match.
  function match(item, raw) {
    var q = (raw || "").toLowerCase().trim();
    if (!q) { return { score: 1, hits: [] }; }
    var label = (item.label || "").toLowerCase();
    var hay = (label + " " + (item.keywords || "") + " " + (item.path_label || "")).toLowerCase();
    var idx = label.indexOf(q);
    if (idx === 0) { return { score: 5, hits: span(idx, q.length) }; }
    if (idx > 0) { return { score: 4, hits: span(idx, q.length) }; }
    if (hay.indexOf(q) !== -1) { return { score: 3, hits: findHits(label, q) }; }
    if (!cfg.fuzzy) { return { score: 0, hits: [] }; }
    // Subsequence fuzzy over the label.
    var hits = [], j = 0;
    for (var i = 0; i < label.length && j < q.length; i++) {
      if (label.charAt(i) === q.charAt(j)) { hits.push(i); j++; }
    }
    return j === q.length ? { score: 2, hits: hits } : { score: 0, hits: [] };
  }
  function span(start, len) { var a = []; for (var i = 0; i < len; i++) { a.push(start + i); } return a; }
  function findHits(label, q) { var i = label.indexOf(q); return i === -1 ? [] : span(i, q.length); }

  /* ---- DOM-safe rendering ---- */

  function highlightInto(parent, label, hits) {
    if (!hits || !hits.length) { parent.appendChild(document.createTextNode(label)); return; }
    var set = {}; hits.forEach(function (h) { set[h] = true; });
    var buf = "", marking = false;
    function flush() {
      if (!buf) { return; }
      if (marking) {
        var mk = document.createElement("mark");
        mk.className = "rmc-cmdk__mark";
        mk.textContent = buf;
        parent.appendChild(mk);
      } else {
        parent.appendChild(document.createTextNode(buf));
      }
      buf = "";
    }
    for (var i = 0; i < label.length; i++) {
      var on = !!set[i];
      if (on !== marking) { flush(); marking = on; }
      buf += label.charAt(i);
    }
    flush();
  }

  function bandHeader(text) {
    var li = document.createElement("li");
    li.className = "rmc-cmdk__band";
    li.setAttribute("role", "presentation");
    li.textContent = text;
    return li;
  }

  function itemRow(item, idx, hits) {
    var li = document.createElement("li");
    li.className = "rmc-cmdk__item" + (idx === state.activeIndex ? " is-active" : "") + (item.locked ? " is-locked" : "");
    li.setAttribute("role", "option");
    li.id = "rmc-cmdk-item-" + idx;
    li.setAttribute("aria-selected", idx === state.activeIndex ? "true" : "false");
    li.dataset.idx = String(idx);
    if (item.source) { li.dataset.src = item.source; }

    var icon = document.createElement("i");
    icon.className = "bi " + (item.icon || "bi-arrow-right-circle") + " rmc-cmdk__item-icon";
    icon.setAttribute("aria-hidden", "true");
    li.appendChild(icon);

    var body = document.createElement("span");
    body.className = "rmc-cmdk__item-body";
    var labelEl = document.createElement("span");
    labelEl.className = "rmc-cmdk__item-label";
    highlightInto(labelEl, item.label || "", hits);
    body.appendChild(labelEl);
    var sub = item.path_label || item.detail || "";
    if (item.locked && item.missing_permission) { sub = "Requires " + item.missing_permission; }
    if (sub) {
      var subEl = document.createElement("span");
      subEl.className = "rmc-cmdk__item-sub";
      subEl.textContent = sub;
      body.appendChild(subEl);
    }
    li.appendChild(body);

    if (item.source) {
      var src = document.createElement("span");
      src.className = "rmc-cmdk__src";
      src.dataset.src = item.source;
      src.textContent = item.source.toUpperCase();
      li.appendChild(src);
    }

    // Pin affordance (only for real navigations, not transient AI/actions).
    if (item.url) {
      var pin = document.createElement("button");
      pin.type = "button";
      pin.className = "rmc-cmdk__pin" + (isPinned(item.url) ? " is-on" : "");
      pin.setAttribute("aria-label", isPinned(item.url) ? "Unpin" : "Pin to top");
      pin.setAttribute("aria-pressed", isPinned(item.url) ? "true" : "false");
      pin.dataset.pin = item.url;
      pin.textContent = "★";
      li.appendChild(pin);
    }
    return li;
  }

  // Render the engine list from ordered sections [{band, items:[{item,hits}]}].
  function renderSections(sections) {
    var list = document.getElementById(LIST_ID);
    if (!list) { return; }
    list.textContent = "";
    state.filtered = [];
    sections.forEach(function (sec) {
      if (!sec.items.length) { return; }
      if (sec.band) { list.appendChild(bandHeader(sec.band)); }
      sec.items.forEach(function (entry) {
        var idx = state.filtered.length;
        state.filtered.push(entry.item);
        list.appendChild(itemRow(entry.item, idx, entry.hits));
      });
    });
    if (!state.filtered.length) {
      var empty = document.createElement("li");
      empty.className = "rmc-cmdk__empty";
      empty.textContent = "No matches.";
      list.appendChild(empty);
    }
    var input = document.getElementById(INPUT_ID);
    if (input && state.activeIndex >= 0 && state.filtered.length) {
      input.setAttribute("aria-activedescendant", "rmc-cmdk-item-" + state.activeIndex);
    }
  }

  /* ---- pool assembly + filtering ---- */

  function buildPool() {
    var pool = state.staticItems
      .concat(state.registryItems)
      .concat(cfg.federateSidebar ? state.sidebarItems : [])
      .concat(state.remoteItems);
    // Dedupe by url (first wins); url-less action items always kept.
    var seen = {}, out = [];
    pool.forEach(function (it) {
      if (it.url) {
        if (seen[it.url]) { return; }
        seen[it.url] = true;
      }
      out.push(it);
    });
    return out;
  }

  var SOURCE_ORDER = ["nav", "action", "sidebar", "ai"];
  var SOURCE_BANDS = { nav: "Navigate", action: "Actions", sidebar: "Sidebar", ai: "AI" };

  function refilter() {
    var pool = buildPool();
    var q = (state.query || "").trim();

    if (!q) {
      renderSections(emptySections(pool));
    } else {
      var scored = pool
        .map(function (it) { var m = match(it, q); return { item: it, hits: m.hits, score: m.score }; })
        .filter(function (x) { return x.score > 0; });
      if (cfg.adaptive) {
        var usage = readUsage();
        scored.sort(function (a, b) {
          return (b.score - a.score) || ((usage[b.item.url] || 0) - (usage[a.item.url] || 0));
        });
      } else {
        scored.sort(function (a, b) { return b.score - a.score; });
      }
      scored = scored.slice(0, RESULTS_MAX);
      var sections;
      if (cfg.adaptive) {
        var byKey = {};
        scored.forEach(function (x) {
          var k = SOURCE_BANDS[x.item.source] ? x.item.source : "nav";
          (byKey[k] || (byKey[k] = [])).push({ item: x.item, hits: x.hits });
        });
        sections = SOURCE_ORDER.map(function (k) { return { band: SOURCE_BANDS[k], items: byKey[k] || [] }; })
          .filter(function (s) { return s.items.length; });
      } else {
        sections = [{ band: "", items: scored.map(function (x) { return { item: x.item, hits: x.hits }; }) }];
      }
      if (!scored.length) { sections = [{ band: "AI", items: [{ item: askAiItem(q), hits: [] }] }]; }
      renderSections(sections);
    }
    state.activeIndex = state.filtered.length ? 0 : -1;
    syncActive();
  }

  function emptySections(pool) {
    if (!cfg.adaptive) {
      return [{ band: "", items: pool.slice(0, RESULTS_MAX).map(function (it) { return { item: it, hits: [] }; }) }];
    }
    var byUrl = {};
    pool.forEach(function (it) { if (it.url && !byUrl[it.url]) { byUrl[it.url] = it; } });
    var usage = readUsage();
    var used = {};

    var pinned = readPinned().map(function (u) { return byUrl[u]; }).filter(Boolean);
    pinned.forEach(function (it) { used[it.url] = true; });

    var frequent = Object.keys(usage)
      .filter(function (u) { return byUrl[u] && !used[u] && usage[u] >= FREQUENT_MIN_HITS; })
      .sort(function (a, b) { return usage[b] - usage[a]; })
      .slice(0, FREQUENT_MAX)
      .map(function (u) { used[u] = true; return byUrl[u]; });

    var recent = recentItems().filter(function (it) { return !used[it.url]; }).slice(0, RECENT_MAX);
    recent.forEach(function (it) { if (it.url) { used[it.url] = true; } });

    var sections = [
      { band: "★ Pinned", items: wrap(pinned) },
      { band: "Frequent", items: wrap(frequent) },
      { band: "Recent", items: wrap(recent) },
    ];
    // Remaining pool, grouped by source.
    var byKey = {};
    pool.forEach(function (it) {
      if (it.url && used[it.url]) { return; }
      var k = SOURCE_BANDS[it.source] ? it.source : "nav";
      (byKey[k] || (byKey[k] = [])).push({ item: it, hits: [] });
    });
    SOURCE_ORDER.forEach(function (k) {
      if (byKey[k] && byKey[k].length) { sections.push({ band: SOURCE_BANDS[k], items: byKey[k] }); }
    });
    return sections;
  }
  function wrap(items) { return items.map(function (it) { return { item: it, hits: [] }; }); }

  /* ---- selection + activation ---- */

  function syncActive() {
    var list = document.getElementById(LIST_ID);
    if (!list) { return; }
    var rows = list.querySelectorAll(".rmc-cmdk__item");
    Array.prototype.forEach.call(rows, function (li) {
      var on = parseInt(li.dataset.idx, 10) === state.activeIndex;
      li.classList.toggle("is-active", on);
      li.setAttribute("aria-selected", on ? "true" : "false");
      if (on) { try { li.scrollIntoView({ block: "nearest" }); } catch (_) {} }
    });
    var input = document.getElementById(INPUT_ID);
    if (input && state.activeIndex >= 0 && state.filtered.length) {
      input.setAttribute("aria-activedescendant", "rmc-cmdk-item-" + state.activeIndex);
    }
  }

  function activate(item) {
    if (!item || item.locked) { return; }
    if (item.url) {
      bumpUsage(item);
      pushRecent(item);
      window.location.href = item.url;
      return;
    }
    if (item.action) {
      try { window.dispatchEvent(new CustomEvent(item.action)); } catch (_) {}
      close();
    }
  }

  function open() {
    if (!cfg.enabled) { return; }
    var root = document.getElementById(ROOT_ID);
    if (!root || state.open) { return; }
    state.open = true;
    root.hidden = false;
    document.body.classList.add("rmc-cmdk-open");
    var input = document.getElementById(INPUT_ID);
    if (input) {
      input.value = "";
      state.query = "";
      state.remoteItems = [];
      refilter();
      setTimeout(function () { input.focus(); }, 0);
    }
  }

  function close() {
    var root = document.getElementById(ROOT_ID);
    if (!root || !state.open) { return; }
    state.open = false;
    root.hidden = true;
    document.body.classList.remove("rmc-cmdk-open");
    if (state.remoteTimer) { clearTimeout(state.remoteTimer); }
  }

  /* ---- remote + registry fetch ---- */

  function fetchRegistry() {
    var url = config.actions_url || "";
    if (!url) { return; }
    try {
      var req = new XMLHttpRequest();
      req.open("GET", url, true);
      req.setRequestHeader("Accept", "application/json");
      req.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      req.onreadystatechange = function () {
        if (req.readyState !== 4) { return; }
        if (req.status >= 200 && req.status < 300) {
          try {
            var payload = JSON.parse(req.responseText || "{}");
            if (payload && Array.isArray(payload.actions)) {
              state.registryItems = mapRegistry(payload.actions);
              if (state.open) { refilter(); }
            }
          } catch (_) {}
        }
      };
      req.send(null);
    } catch (_) {}
  }

  function fetchRemote(q) {
    if (!config.api_url || q.length < 2) {
      state.remoteItems = [];
      refilter();
      return;
    }
    var fetchId = ++state.remoteFetchId;
    var activePath = (window.location.pathname || "/") + (window.location.search || "");
    try { sessionStorage.setItem("rmc:cmdk:active_url", activePath); } catch (_) {}
    fetch(config.api_url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ q: q, active_url: activePath, include_ai: q.length >= 4 ? "1" : "0" }),
    })
      .then(function (r) { return r.json(); })
      .then(function (payload) {
        if (fetchId !== state.remoteFetchId) { return; }
        state.remoteItems = ((payload && payload.results) || []).map(mapRemote);
        refilter();
      })
      .catch(function () {
        if (fetchId !== state.remoteFetchId) { return; }
        state.remoteItems = [];
        refilter();
      });
  }

  function scheduleRemote(q) {
    if (state.remoteTimer) { clearTimeout(state.remoteTimer); }
    state.remoteTimer = setTimeout(function () { fetchRemote(q); }, 220);
  }

  /* ---- events ---- */

  function onKeydown(e) {
    var isMod = e.metaKey || e.ctrlKey;
    if (isMod && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (state.open) { close(); } else { open(); }
      return;
    }
    if (!state.open) { return; }
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (state.filtered.length) { state.activeIndex = (state.activeIndex + 1) % state.filtered.length; syncActive(); }
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (state.filtered.length) { state.activeIndex = (state.activeIndex - 1 + state.filtered.length) % state.filtered.length; syncActive(); }
      return;
    }
    if (e.key === "Enter") { e.preventDefault(); activate(state.filtered[state.activeIndex]); }
  }

  function onInput(e) {
    state.query = e.target.value || "";
    refilter();
    scheduleRemote(state.query.trim());
  }

  function onListClick(e) {
    if (!e.target || !e.target.closest) { return; }
    var pin = e.target.closest(".rmc-cmdk__pin");
    if (pin) {
      e.preventDefault();
      e.stopPropagation();
      togglePin(pin.dataset.pin);
      refilter();
      return;
    }
    var li = e.target.closest(".rmc-cmdk__item");
    if (!li || li.classList.contains("is-locked")) { return; }
    var idx = parseInt(li.dataset.idx, 10);
    if (!isNaN(idx)) { activate(state.filtered[idx]); }
  }

  function init() {
    config = readData();
    readFlags();
    if (!cfg.enabled) {
      // Operator disabled the palette platform-wide. Keep ⌘K bound to a no-op
      // (open() early-returns) so nothing else hijacks it, but build nothing.
      document.addEventListener("keydown", onKeydown, false);
      window.RMCCommandPalette = { open: open, close: close, disabled: true };
      return;
    }

    state.staticItems = flattenItems(config.groups);
    try { state.sidebarItems = harvestSidebar(); } catch (_) { state.sidebarItems = []; }
    refilter();
    fetchRegistry();

    document.addEventListener("keydown", onKeydown, false);
    var input = document.getElementById(INPUT_ID);
    if (input) { input.addEventListener("input", onInput); }
    var list = document.getElementById(LIST_ID);
    if (list) { list.addEventListener("click", onListClick); }
    var backdrop = document.querySelector("[data-rmc-cmdk-dismiss]");
    if (backdrop) { backdrop.addEventListener("click", close); }

    window.addEventListener("rmc:cmdk:toggle-theme", function () {
      if (!window.RMCTheme) { return; }
      var pref = window.RMCTheme.get();
      var next = pref === "light" ? "dark" : (pref === "dark" ? "system" : "light");
      window.RMCTheme.set(next);
    });
    window.addEventListener("rmc:cmdk:open-ai", function () {
      if (config.ai_center_url) { window.location.href = config.ai_center_url; return; }
      var t = document.getElementById("aiCopilotTrigger");
      if (t) { t.click(); }
    });
    window.addEventListener("rmc:cmdk:ask-ai", function () {
      var q = (state.query || "").trim();
      if (config.ai_center_url && q) {
        var sep = config.ai_center_url.indexOf("?") >= 0 ? "&" : "?";
        var active = "";
        try { active = sessionStorage.getItem("rmc:cmdk:active_url") || ""; } catch (_) {}
        if (!active && window.location) { active = (window.location.pathname || "") + (window.location.search || ""); }
        var href = config.ai_center_url + sep + "assistant=first_line_support&q=" + encodeURIComponent(q);
        if (active) { href += "&active_url=" + encodeURIComponent(active); }
        window.location.href = href;
        return;
      }
      var trigger = document.getElementById("aiCopilotTrigger");
      if (trigger) { trigger.click(); }
      setTimeout(function () {
        var copilotInput = document.getElementById("aiCopilotInput");
        if (copilotInput) {
          copilotInput.value = q;
          try { copilotInput.dispatchEvent(new Event("input", { bubbles: true })); } catch (_) {}
          copilotInput.focus();
        }
      }, 80);
    });

    /* Quick-action chips ([data-rmc-cmdk-open] + optional [data-rmc-cmdk-prefix]
       mode token like ":new ") open the palette and seed a plain search term. */
    document.addEventListener("click", function (e) {
      var chip = e.target && e.target.closest ? e.target.closest("[data-rmc-cmdk-open]") : null;
      if (!chip) { return; }
      e.preventDefault();
      open();
      var seed = (chip.getAttribute("data-rmc-cmdk-prefix") || "").trim().replace(/^:/, "").trim();
      if (!seed) { return; }
      var seedInput = document.getElementById(INPUT_ID);
      if (seedInput) {
        seedInput.value = seed;
        try { seedInput.dispatchEvent(new Event("input", { bubbles: true })); } catch (_) {}
      }
    }, false);

    window.RMCCommandPalette = { open: open, close: close };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
