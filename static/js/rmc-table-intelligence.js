/**
 * RunMyCampus Table Intelligence (v4.04.60) — ONE engine, every list page.
 *
 * Progressive enhancement that auto-attaches to every `table.rmc-data-table`
 * already on the page (377+ templates carry that class) — so it lights up
 * platform-wide with ZERO per-page edits. A table opts out with
 * `data-rmc-smart-table="0"`. It COMPOSES with the existing systems (bulk-select
 * `rmc-list-bulk-select.js`, density CSS in `table-system.css`, the row-detail
 * drawer) — it does not replace them.
 *
 * Adds the gaps the audit found: instant client-side filter (with CSP-safe
 * <mark> highlight in plain-text cells only), click-to-sort columns with
 * aria-sort (text/number/date aware), per-user column show/hide + density,
 * ↑/↓/↵ keyboard row nav, and client CSV export of the visible rows.
 *
 * Config comes from the SITE cascade via the #rmc-tables-config island
 * (default-on, operator/school overridable). Everything is wrapped in try/catch
 * so a table always degrades to its server-rendered self.
 */
(function () {
  "use strict";

  var PREFS_KEY = "rmcTablePrefs:v1";
  var MIN_ROWS_FOR_BAR = 6;     // tiny tables stay clean (sort/keyboard still on)
  var DENSITIES = ["compact", "comfortable", "spacious"];

  var cfg = { intelligence: true, filter: true, sort: true, columns: true, export: true, density: "comfortable" };

  function readConfig() {
    var node = document.getElementById("rmc-tables-config");
    if (!node || !node.textContent) { return; }
    try {
      var d = JSON.parse(node.textContent);
      ["intelligence", "filter", "sort", "columns", "export"].forEach(function (k) {
        if (d[k] === false || d[k] === 0 || d[k] === "0") { cfg[k] = false; }
      });
      if (typeof d.density === "string" && DENSITIES.indexOf(d.density) !== -1) { cfg.density = d.density; }
    } catch (_) {}
  }

  /* ---- per-user prefs (localStorage, keyed per table) ---- */
  function allPrefs() {
    try { return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") || {}; } catch (_) { return {}; }
  }
  function tableKey(table) {
    if (table.id) { return table.id; }
    var heads = [];
    var ths = table.querySelectorAll("thead th");
    Array.prototype.forEach.call(ths, function (th) { heads.push((th.textContent || "").trim().slice(0, 12)); });
    return (location.pathname + "::" + heads.join("|")).slice(0, 160);
  }
  function getPrefs(key) { var p = allPrefs(); return p[key] || {}; }
  function setPrefs(key, prefs) {
    var p = allPrefs();
    p[key] = prefs;
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch (_) {}
  }

  /* ---- helpers ---- */
  function headerCells(table) {
    var thead = table.querySelector("thead");
    if (!thead) { return []; }
    var rows = thead.querySelectorAll("tr");
    if (!rows.length) { return []; }
    return Array.prototype.slice.call(rows[rows.length - 1].children).filter(function (c) {
      return c.tagName === "TH" || c.tagName === "TD";
    });
  }
  function bodyRows(table) {
    var tbody = table.querySelector("tbody");
    if (!tbody) { return []; }
    return Array.prototype.filter.call(tbody.children, function (r) { return r.tagName === "TR"; });
  }
  function cellText(cell) { return (cell.textContent || "").replace(/\s+/g, " ").trim(); }

  function inferType(table, colIndex) {
    var rows = bodyRows(table), nums = 0, seen = 0;
    for (var i = 0; i < rows.length && seen < 12; i++) {
      var cell = rows[i].children[colIndex];
      if (!cell) { continue; }
      var t = cellText(cell).replace(/[$,%\s]/g, "");
      if (t === "") { continue; }
      seen++;
      if (!isNaN(parseFloat(t)) && isFinite(t)) { nums++; }
    }
    return seen > 0 && nums === seen ? "num" : "text";
  }

  function highlightCell(cell, needle) {
    // Only touch plain-text cells (single text node) so we never mangle markup
    // (chips, links, buttons). Other cells just match without visual highlight.
    if (!needle || cell.childNodes.length !== 1 || cell.firstChild.nodeType !== 3) { return; }
    var text = cell.firstChild.nodeValue, low = text.toLowerCase(), i = low.indexOf(needle);
    if (i < 0) { return; }
    var frag = document.createDocumentFragment();
    frag.appendChild(document.createTextNode(text.slice(0, i)));
    var mk = document.createElement("mark");
    mk.className = "rmc-tbl-mark";
    mk.textContent = text.slice(i, i + needle.length);
    frag.appendChild(mk);
    frag.appendChild(document.createTextNode(text.slice(i + needle.length)));
    cell.textContent = "";
    cell.appendChild(frag);
    cell.dataset.rmcHl = "1";
  }
  function clearHighlight(cell) {
    if (cell.dataset.rmcHl !== "1") { return; }
    cell.textContent = cell.textContent; // collapse <mark> back to plain text
    delete cell.dataset.rmcHl;
  }

  /* ---- per-table enhancement ---- */
  function enhance(table) {
    if (table.dataset.rmcSmartTable === "0" || table.dataset.rmcTableReady === "1") { return; }
    table.dataset.rmcTableReady = "1";

    var key = tableKey(table);
    var prefs = getPrefs(key);
    var heads = headerCells(table);
    var ncols = heads.length;
    var rows = bodyRows(table);

    // density (per-user pref over cascade default)
    var density = DENSITIES.indexOf(prefs.density) !== -1 ? prefs.density : cfg.density;
    table.setAttribute("data-density", density);

    // restore hidden columns
    var hidden = {};
    (prefs.hidden || []).forEach(function (idx) { hidden[idx] = true; });
    function applyColVisibility() {
      heads.forEach(function (th, ci) { th.classList.toggle("rmc-tbl-col-hidden", !!hidden[ci]); });
      rows.forEach(function (tr) {
        Array.prototype.forEach.call(tr.children, function (td, ci) { td.classList.toggle("rmc-tbl-col-hidden", !!hidden[ci]); });
      });
    }
    applyColVisibility();

    var state = { sortCol: null, sortDir: 1, cursor: -1, q: "" };

    /* sort */
    function sortBy(ci) {
      if (state.sortCol === ci) { state.sortDir = -state.sortDir; } else { state.sortCol = ci; state.sortDir = 1; }
      var type = inferType(table, ci);
      var tbody = table.querySelector("tbody");
      var visible = bodyRows(table);
      visible.sort(function (a, b) {
        var x = cellText(a.children[ci] || {}), y = cellText(b.children[ci] || {});
        if (type === "num") { x = parseFloat(x.replace(/[$,%\s]/g, "")) || 0; y = parseFloat(y.replace(/[$,%\s]/g, "")) || 0; }
        else { x = x.toLowerCase(); y = y.toLowerCase(); }
        return (x < y ? -1 : x > y ? 1 : 0) * state.sortDir;
      });
      visible.forEach(function (r) { tbody.appendChild(r); });
      heads.forEach(function (th, idx) {
        th.classList.toggle("rmc-tbl-sorted", idx === ci);
        if (idx === ci) { th.setAttribute("aria-sort", state.sortDir > 0 ? "ascending" : "descending"); }
        else { th.removeAttribute("aria-sort"); }
      });
      rows = bodyRows(table);
    }
    if (cfg.sort && ncols) {
      heads.forEach(function (th, ci) {
        if (th.dataset.rmcNoSort === "1") { return; }
        th.classList.add("rmc-tbl-sortable");
        if (!th.hasAttribute("scope")) { th.setAttribute("scope", "col"); }
        th.addEventListener("click", function (e) {
          if (e.target.closest("input,button,a")) { return; }
          sortBy(ci);
        });
      });
    }

    /* filter */
    function applyFilter() {
      var needle = state.q.toLowerCase().trim();
      var shown = 0;
      bodyRows(table).forEach(function (tr) {
        Array.prototype.forEach.call(tr.children, clearHighlight);
        var match = !needle || (tr.textContent || "").toLowerCase().indexOf(needle) !== -1;
        tr.classList.toggle("rmc-tbl-row-hidden", !match);
        if (match) {
          shown++;
          if (needle) { Array.prototype.forEach.call(tr.children, function (td) { highlightCell(td, needle); }); }
        }
      });
      if (bar) { bar.count.textContent = needle ? (shown + " of " + rows.length) : (rows.length + " rows"); }
      state.cursor = -1;
      paintCursor();
    }

    /* keyboard cursor */
    function visibleRows() { return bodyRows(table).filter(function (r) { return !r.classList.contains("rmc-tbl-row-hidden"); }); }
    function paintCursor() {
      var vis = visibleRows();
      bodyRows(table).forEach(function (r) { r.classList.remove("rmc-tbl-cur"); });
      if (state.cursor >= 0 && state.cursor < vis.length) {
        var r = vis[state.cursor];
        r.classList.add("rmc-tbl-cur");
        try { r.scrollIntoView({ block: "nearest" }); } catch (_) {}
      }
    }
    function moveCursor(delta) {
      var vis = visibleRows();
      if (!vis.length) { return; }
      state.cursor = Math.max(0, Math.min(vis.length - 1, (state.cursor < 0 ? 0 : state.cursor + delta)));
      paintCursor();
    }
    function openCursor() {
      var vis = visibleRows();
      if (state.cursor < 0 || state.cursor >= vis.length) { return; }
      var r = vis[state.cursor];
      var link = r.querySelector("a[href]");
      if (link) { link.click(); return; }
      r.click();
    }

    /* toolbar (only for tables big enough to warrant it) */
    var bar = null;
    if (rows.length >= MIN_ROWS_FOR_BAR && (cfg.filter || cfg.columns || cfg.export)) {
      bar = buildBar(table, {
        cfg: cfg, density: density, heads: heads, hidden: hidden,
        onFilter: function (v) { state.q = v; applyFilter(); },
        onDensity: function (v) { table.setAttribute("data-density", v); prefs.density = v; setPrefs(key, prefs); },
        onToggleCol: function (ci, show) {
          hidden[ci] = !show;
          prefs.hidden = Object.keys(hidden).filter(function (k2) { return hidden[k2]; }).map(Number);
          setPrefs(key, prefs);
          applyColVisibility();
        },
        onExport: function () { exportCsv(table, heads, hidden); },
      });
    }

    /* keyboard nav: bound on the table; ignores typing in inputs */
    table.addEventListener("keydown", function (e) {
      var inField = e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable);
      if (inField && e.target.classList && e.target.classList.contains("rmc-tbl-bar__input")) {
        if (e.key === "ArrowDown") { e.preventDefault(); table.focus(); moveCursor(1); }
        return;
      }
      if (inField) { return; }
      if (e.key === "ArrowDown") { e.preventDefault(); moveCursor(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); moveCursor(-1); }
      else if (e.key === "Enter") { openCursor(); }
    });
    if (!table.hasAttribute("tabindex")) { table.setAttribute("tabindex", "-1"); }

    if (bar) { bar.count.textContent = rows.length + " rows"; }
  }

  /* ---- toolbar builder (CSP-safe; createElement only) ---- */
  function buildBar(table, opts) {
    var bar = document.createElement("div");
    bar.className = "rmc-tbl-bar";
    bar.setAttribute("role", "toolbar");

    var count = document.createElement("span");
    count.className = "rmc-tbl-bar__count";

    if (opts.cfg.filter) {
      var fwrap = document.createElement("div");
      fwrap.className = "rmc-tbl-bar__filter";
      var input = document.createElement("input");
      input.type = "search";
      input.className = "rmc-tbl-bar__input";
      input.setAttribute("placeholder", "Filter these results…");
      input.setAttribute("aria-label", "Filter the rows on this page");
      input.addEventListener("input", function () { opts.onFilter(input.value || ""); });
      fwrap.appendChild(input);
      bar.appendChild(fwrap);
    }
    bar.appendChild(count);

    // density segmented control
    var seg = document.createElement("div");
    seg.className = "rmc-tbl-seg";
    seg.setAttribute("role", "group");
    seg.setAttribute("aria-label", "Row density");
    [["compact", "Compact"], ["comfortable", "Cozy"], ["spacious", "Roomy"]].forEach(function (d) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "rmc-tbl-seg__btn";
      b.textContent = d[1];
      b.setAttribute("aria-pressed", d[0] === opts.density ? "true" : "false");
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(seg.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        opts.onDensity(d[0]);
      });
      seg.appendChild(b);
    });
    bar.appendChild(seg);

    // columns popover
    if (opts.cfg.columns && opts.heads.length) {
      var pop = document.createElement("div");
      pop.className = "rmc-tbl-pop";
      var gear = document.createElement("button");
      gear.type = "button";
      gear.className = "rmc-tbl-gear";
      gear.textContent = "⚙ Columns";
      gear.setAttribute("aria-expanded", "false");
      var menu = document.createElement("div");
      menu.className = "rmc-tbl-menu";
      opts.heads.forEach(function (th, ci) {
        var label = document.createElement("label");
        label.className = "rmc-tbl-menu__item";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !opts.hidden[ci];
        cb.addEventListener("change", function () { opts.onToggleCol(ci, cb.checked); });
        label.appendChild(cb);
        label.appendChild(document.createTextNode(" " + (cellText(th) || ("Column " + (ci + 1)))));
        menu.appendChild(label);
      });
      gear.addEventListener("click", function (e) {
        e.stopPropagation();
        var open = pop.classList.toggle("is-open");
        gear.setAttribute("aria-expanded", open ? "true" : "false");
      });
      menu.addEventListener("click", function (e) { e.stopPropagation(); });
      document.addEventListener("click", function () { pop.classList.remove("is-open"); gear.setAttribute("aria-expanded", "false"); });
      pop.appendChild(gear);
      pop.appendChild(menu);
      bar.appendChild(pop);
    }

    // CSV export
    if (opts.cfg.export) {
      var csv = document.createElement("button");
      csv.type = "button";
      csv.className = "rmc-tbl-gear";
      csv.textContent = "⤓ CSV";
      csv.addEventListener("click", opts.onExport);
      bar.appendChild(csv);
    }

    var anchor = table.closest(".table-responsive") || table;
    if (anchor.parentNode) { anchor.parentNode.insertBefore(bar, anchor); }
    return { el: bar, count: count };
  }

  function exportCsv(table, heads, hidden) {
    function esc(s) { s = String(s == null ? "" : s); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
    var lines = [];
    var hdr = [];
    heads.forEach(function (th, ci) { if (!hidden[ci]) { hdr.push(esc(cellText(th))); } });
    lines.push(hdr.join(","));
    bodyRows(table).forEach(function (tr) {
      if (tr.classList.contains("rmc-tbl-row-hidden")) { return; }
      var cells = [];
      Array.prototype.forEach.call(tr.children, function (td, ci) { if (!hidden[ci]) { cells.push(esc(cellText(td))); } });
      lines.push(cells.join(","));
    });
    try {
      var blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "export.csv";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    } catch (_) {}
  }

  function init() {
    readConfig();
    if (!cfg.intelligence) { return; }
    var tables = document.querySelectorAll("table.rmc-data-table");
    Array.prototype.forEach.call(tables, function (t) {
      try { enhance(t); } catch (_) {}
    });
    window.RMCTableIntelligence = { enhance: enhance };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
