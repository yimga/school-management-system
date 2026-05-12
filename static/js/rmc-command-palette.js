/**
 * RunMyCampus Command Palette (⌘K / Ctrl+K)
 *
 * Apple Spotlight-style palette mounted globally on every authenticated shell.
 * Lets users jump to any page, fire an action, or open the AI copilot — the
 * platform-wide answer to "long, endless nav."
 *
 * Markup contract: templates/components/rmc_command_palette.html
 * Data contract: <script type="application/json" id="rmc-cmdk-data"> defines
 * groups and items. Items have either `url` (navigate) or `action` (CustomEvent name).
 */
(function () {
  "use strict";

  var ROOT_ID = "rmc-cmdk";
  var INPUT_ID = "rmc-cmdk-input";
  var LIST_ID = "rmc-cmdk-list";
  var DATA_ID = "rmc-cmdk-data";

  function readData() {
    var node = document.getElementById(DATA_ID);
    if (!node || !node.textContent) { return { groups: [] }; }
    try { return JSON.parse(node.textContent); } catch (_) { return { groups: [] }; }
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
        });
      });
    });
    return items;
  }

  /* Improvement C (2026-05-12): Recent list — persists last 6 destinations in
     localStorage so users land in the same place they did last time. */
  var RECENT_KEY = "rmc-cmdk:recent";
  var RECENT_MAX = 6;
  function readRecent() {
    try {
      var raw = localStorage.getItem(RECENT_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (_) { return []; }
  }
  function pushRecent(item) {
    if (!item || !item.url) { return; }
    var recent = readRecent().filter(function (r) { return r.url !== item.url; });
    recent.unshift({ label: item.label, url: item.url, icon: item.icon });
    recent = recent.slice(0, RECENT_MAX);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(recent)); } catch (_) {}
  }
  function recentItems() {
    return readRecent().map(function (r) {
      return Object.assign({}, r, { group: "Recent", keywords: "recent " + (r.label || "") });
    });
  }

  function score(item, query) {
    if (!query) { return 1; }
    var q = query.toLowerCase().trim();
    var hay = (item.label + " " + item.keywords).toLowerCase();
    if (hay.indexOf(q) === -1) { return 0; }
    /* Heavier weight for label prefix, then label contains, then keyword contains. */
    if (item.label.toLowerCase().indexOf(q) === 0) { return 3; }
    if (item.label.toLowerCase().indexOf(q) !== -1) { return 2; }
    return 1;
  }

  var state = {
    open: false,
    query: "",
    items: [],
    filtered: [],
    activeIndex: 0,
  };

  function render() {
    var list = document.getElementById(LIST_ID);
    if (!list) { return; }
    list.innerHTML = "";
    if (!state.filtered.length) {
      list.innerHTML = '<li class="rmc-cmdk__empty">No matches.</li>';
      return;
    }
    state.filtered.forEach(function (item, idx) {
      var li = document.createElement("li");
      li.className = "rmc-cmdk__item" + (idx === state.activeIndex ? " is-active" : "");
      li.setAttribute("role", "option");
      li.id = "rmc-cmdk-item-" + idx;
      li.setAttribute("aria-selected", idx === state.activeIndex ? "true" : "false");
      li.dataset.idx = String(idx);
      li.innerHTML =
        '<i class="bi ' + item.icon + ' rmc-cmdk__item-icon" aria-hidden="true"></i>' +
        '<span class="rmc-cmdk__item-label">' + escapeHtml(item.label) + '</span>' +
        '<span class="rmc-cmdk__item-group">' + escapeHtml(item.group) + '</span>';
      list.appendChild(li);
    });
    var input = document.getElementById(INPUT_ID);
    if (input) {
      input.setAttribute("aria-activedescendant", "rmc-cmdk-item-" + state.activeIndex);
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function refilter() {
    var scored = state.items
      .map(function (it) { return { it: it, s: score(it, state.query) }; })
      .filter(function (x) { return x.s > 0; })
      .sort(function (a, b) { return b.s - a.s; })
      .map(function (x) { return x.it; });
    state.filtered = scored;
    state.activeIndex = scored.length ? 0 : -1;
    render();
  }

  function activate(item) {
    if (!item) { return; }
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
  }

  function onKeydown(e) {
    /* Global ⌘K / Ctrl+K to open. */
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
  }

  function onListClick(e) {
    var li = e.target.closest && e.target.closest(".rmc-cmdk__item");
    if (!li) { return; }
    var idx = parseInt(li.dataset.idx, 10);
    if (!isNaN(idx)) {
      activate(state.filtered[idx]);
    }
  }

  function init() {
    var data = readData();
    var base = flattenItems(data.groups);
    /* Prepend Recent group when present and query is empty — recency-first when
       the user hasn't typed anything. The filter logic re-sorts on input so
       Recent doesn't pollute keyword matches. */
    state.items = recentItems().concat(base);
    state.filtered = state.items.slice();
    render();
    document.addEventListener("keydown", onKeydown, false);
    var input = document.getElementById(INPUT_ID);
    if (input) { input.addEventListener("input", onInput); }
    var list = document.getElementById(LIST_ID);
    if (list) { list.addEventListener("click", onListClick); }
    var backdrop = document.querySelector("[data-rmc-cmdk-dismiss]");
    if (backdrop) { backdrop.addEventListener("click", close); }

    /* Built-in actions */
    window.addEventListener("rmc:cmdk:toggle-theme", function () {
      if (!window.RMCTheme) { return; }
      var pref = window.RMCTheme.get();
      var next = pref === "light" ? "dark" : (pref === "dark" ? "system" : "light");
      window.RMCTheme.set(next);
    });
    window.addEventListener("rmc:cmdk:open-ai", function () {
      var t = document.getElementById("aiCopilotTrigger");
      if (t) { t.click(); }
    });

    /* Expose for other scripts (e.g. nav buttons). */
    window.RMCCommandPalette = { open: open, close: close };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
