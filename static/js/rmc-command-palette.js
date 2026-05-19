/**
 * RunMyCampus Command Palette (⌘K / Ctrl+K) — topology + engine-room aware.
 */
(function () {
  "use strict";

  var ROOT_ID = "rmc-cmdk";
  var INPUT_ID = "rmc-cmdk-input";
  var LIST_ID = "rmc-cmdk-list";
  var DATA_ID = "rmc-cmdk-data";
  var RECENT_KEY = "rmc-cmdk:recent";
  var RECENT_MAX = 6;

  var config = { groups: [], api_url: "", ai_center_url: "" };
  var state = {
    open: false,
    query: "",
    staticItems: [],
    remoteItems: [],
    filtered: [],
    activeIndex: 0,
    remoteTimer: null,
    remoteFetchId: 0,
  };

  function readData() {
    var node = document.getElementById(DATA_ID);
    if (!node || !node.textContent) { return { groups: [] }; }
    try { return JSON.parse(node.textContent); } catch (_) { return { groups: [] }; }
  }

  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }

  function flattenItems(groups) {
    var items = [];
    (groups || []).forEach(function (g) {
      (g.items || []).forEach(function (it) {
        if (!it || (!it.url && !it.action)) { return; }
        items.push({
          label: it.label || "",
          url: it.url || null,
          action: it.action || null,
          icon: it.icon || "bi-arrow-right-circle",
          keywords: (it.keywords || "") + " " + (g.label || ""),
          group: g.label || "",
          locked: false,
        });
      });
    });
    return items;
  }

  function readRecent() {
    try {
      var raw = localStorage.getItem(RECENT_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (_) { return []; }
  }

  function pushRecent(item) {
    if (!item || !item.url || item.locked) { return; }
    var recent = readRecent().filter(function (r) { return r.url !== item.url; });
    recent.unshift({ label: item.label, url: item.url, icon: item.icon });
    recent = recent.slice(0, RECENT_MAX);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(recent)); } catch (_) {}
  }

  function recentItems() {
    return readRecent().map(function (r) {
      return Object.assign({}, r, { group: "Recent", keywords: "recent " + (r.label || ""), locked: false });
    });
  }

  function score(item, query) {
    if (!query) { return 1; }
    var q = query.toLowerCase().trim();
    var hay = (item.label + " " + (item.keywords || "") + " " + (item.path_label || "")).toLowerCase();
    if (hay.indexOf(q) === -1) { return 0; }
    if (item.label.toLowerCase().indexOf(q) === 0) { return 4; }
    if (item.label.toLowerCase().indexOf(q) !== -1) { return 3; }
    return 2;
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
      group: isEscalate
        ? "Support"
        : row.type === "documentation"
          ? "How-to"
          : row.type === "locked"
            ? "Restricted"
            : "Topology",
      locked: row.type === "locked" || !!row.locked,
      missing_permission: row.missing_permission || "",
    };
  }

  function askAiItem(query) {
    return {
      label: 'Ask AI Center: "' + query + '"',
      url: null,
      action: "rmc:cmdk:ask-ai",
      icon: "bi-stars",
      keywords: "ask ai engine room " + query,
      group: "AI",
      locked: false,
    };
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function render() {
    var list = document.getElementById(LIST_ID);
    if (!list) { return; }
    list.innerHTML = "";
    if (!state.filtered.length) {
      var q = (state.query || "").trim();
      if (q) {
        state.filtered = [askAiItem(q)];
        state.activeIndex = 0;
      } else {
        list.innerHTML = '<li class="rmc-cmdk__empty">No matches.</li>';
        return;
      }
    }
    state.filtered.forEach(function (item, idx) {
      var li = document.createElement("li");
      var classes = "rmc-cmdk__item";
      if (idx === state.activeIndex) { classes += " is-active"; }
      if (item.locked) { classes += " is-locked"; }
      li.className = classes;
      li.setAttribute("role", "option");
      li.id = "rmc-cmdk-item-" + idx;
      li.setAttribute("aria-selected", idx === state.activeIndex ? "true" : "false");
      li.dataset.idx = String(idx);
      var sub = item.path_label || item.detail || "";
      if (item.locked && item.missing_permission) {
        sub = "Requires " + item.missing_permission;
      }
      li.innerHTML =
        '<i class="bi ' + item.icon + ' rmc-cmdk__item-icon" aria-hidden="true"></i>' +
        '<span class="rmc-cmdk__item-body">' +
        '<span class="rmc-cmdk__item-label">' + escapeHtml(item.label) + '</span>' +
        (sub ? '<span class="rmc-cmdk__item-sub">' + escapeHtml(sub) + '</span>' : '') +
        '</span>' +
        '<span class="rmc-cmdk__item-group">' + escapeHtml(item.group) + '</span>';
      list.appendChild(li);
    });
    var input = document.getElementById(INPUT_ID);
    if (input && state.activeIndex >= 0) {
      input.setAttribute("aria-activedescendant", "rmc-cmdk-item-" + state.activeIndex);
    }
  }

  function allItems() {
    return recentItems().concat(state.staticItems).concat(state.remoteItems);
  }

  function refilter() {
    var pool = allItems();
    var q = state.query || "";
    var scored = pool
      .map(function (it) { return { it: it, s: score(it, q) }; })
      .filter(function (x) { return x.s > 0; })
      .sort(function (a, b) { return b.s - a.s; })
      .map(function (x) { return x.it; });
    state.filtered = scored.slice(0, 16);
    state.activeIndex = state.filtered.length ? 0 : -1;
    render();
  }

  function fetchRemote(q) {
    if (!config.api_url || q.length < 2) {
      state.remoteItems = [];
      refilter();
      return;
    }
    var fetchId = ++state.remoteFetchId;
    var activePath =
      (window.location.pathname || "/") + (window.location.search || "");
    try {
      sessionStorage.setItem("rmc:cmdk:active_url", activePath);
    } catch (_) {}
    var body = JSON.stringify({
      q: q,
      active_url: activePath,
      include_ai: q.length >= 4 ? "1" : "0",
    });
    fetch(config.api_url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: body,
    })
      .then(function (r) { return r.json(); })
      .then(function (payload) {
        if (fetchId !== state.remoteFetchId) { return; }
        var rows = (payload && payload.results) || [];
        state.remoteItems = rows.map(mapRemote);
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

  function activate(item) {
    if (!item || item.locked) { return; }
    if (item.url) {
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
      if (state.filtered.length) {
        state.activeIndex = (state.activeIndex + 1) % state.filtered.length;
        render();
      }
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (state.filtered.length) {
        state.activeIndex = (state.activeIndex - 1 + state.filtered.length) % state.filtered.length;
        render();
      }
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      activate(state.filtered[state.activeIndex]);
    }
  }

  function onInput(e) {
    state.query = e.target.value || "";
    refilter();
    scheduleRemote(state.query.trim());
  }

  function onListClick(e) {
    var li = e.target.closest && e.target.closest(".rmc-cmdk__item");
    if (!li || li.classList.contains("is-locked")) { return; }
    var idx = parseInt(li.dataset.idx, 10);
    if (!isNaN(idx)) { activate(state.filtered[idx]); }
  }

  function init() {
    config = readData();
    state.staticItems = flattenItems(config.groups);
    state.filtered = allItems().slice(0, 16);
    render();

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
      if (config.ai_center_url) {
        window.location.href = config.ai_center_url;
        return;
      }
      var t = document.getElementById("aiCopilotTrigger");
      if (t) { t.click(); }
    });
    window.addEventListener("rmc:cmdk:ask-ai", function () {
      var q = (state.query || "").trim();
      if (config.ai_center_url && q) {
        var sep = config.ai_center_url.indexOf("?") >= 0 ? "&" : "?";
        var active = "";
        try {
          active = sessionStorage.getItem("rmc:cmdk:active_url") || "";
        } catch (_) {}
        if (!active && window.location) {
          active =
            (window.location.pathname || "") + (window.location.search || "");
        }
        var href =
          config.ai_center_url +
          sep +
          "assistant=first_line_support&q=" +
          encodeURIComponent(q);
        if (active) {
          href += "&active_url=" + encodeURIComponent(active);
        }
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

    window.RMCCommandPalette = { open: open, close: close };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
