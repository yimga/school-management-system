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
 *
 * v4.04.62 (Surface 4): also owns the two TABLE empty states — a "no matches —
 * clear filter" row when the instant filter hides every row, and a canonical
 * data-empty state when a list renders with zero rows. Both read the
 * #rmc-empty-config island (default-on) so they share the empty engine's switch.
 */
(function () {
  "use strict";

  var PREFS_KEY = "rmcTablePrefs:v1";
  var MIN_ROWS_FOR_BAR = 6;     // tiny tables stay clean (sort/keyboard still on)
  var DENSITIES = ["compact", "comfortable", "spacious"];
  var DENSITY_ALIASES = {
    compact: "compact", cozy: "comfortable", comfortable: "comfortable",
    roomy: "spacious", spacious: "spacious", condensed: "compact", expanded: "spacious"
  };
  var DENSITY_CLASSES = ["table-density-compact", "table-density-comfortable", "table-density-spacious"];

  var cfg = { intelligence: true, filter: true, sort: true, columns: true, export: true, density: "comfortable" };

  // Empty-state intelligence (Surface 4) shares this engine for the two TABLE
  // empty states (filter-to-zero + zero-data), read from the #rmc-empty-config
  // island. Default-on; the empty engine's master switch gates both.
  var emptyCfg = { intelligence: true, table_filter: true, table_data: true };

  function readConfig() {
    var node = document.getElementById("rmc-tables-config");
    if (node && node.textContent) {
      try {
        var d = JSON.parse(node.textContent);
        ["intelligence", "filter", "sort", "columns", "export"].forEach(function (k) {
          if (d[k] === false || d[k] === 0 || d[k] === "0") { cfg[k] = false; }
        });
        if (typeof d.density === "string" && DENSITIES.indexOf(d.density) !== -1) { cfg.density = d.density; }
      } catch (_) {}
    }
    var en = document.getElementById("rmc-empty-config");
    if (en && en.textContent) {
      try {
        var e = JSON.parse(en.textContent);
        ["intelligence", "table_filter", "table_data"].forEach(function (k) {
          if (e[k] === false || e[k] === 0 || e[k] === "0") { emptyCfg[k] = false; }
        });
      } catch (_) {}
    }
  }

  /* ---- CSP-safe canonical empty row (Surface 4) ---- */
  function makeEmptyRow(ncols, kind) {
    var tr = document.createElement("tr");
    tr.className = "rmc-tbl-empty-row";
    tr.setAttribute("data-rmc-empty-kind", kind);
    var td = document.createElement("td");
    td.colSpan = ncols || 1;
    var wrap = document.createElement("div");
    wrap.className = "rmc-empty rmc-empty--row";
    wrap.setAttribute("role", "status");
    var ic = document.createElement("div");
    ic.className = "rmc-empty__icon";
    var i = document.createElement("i");
    i.className = "bi " + (kind === "filter" ? "bi-search" : "bi-inbox");
    i.setAttribute("aria-hidden", "true");
    ic.appendChild(i);
    var h = document.createElement("h3"); h.className = "rmc-empty__title";
    var p = document.createElement("p"); p.className = "rmc-empty__message";
    wrap.appendChild(ic); wrap.appendChild(h); wrap.appendChild(p);
    td.appendChild(wrap); tr.appendChild(td);
    return { tr: tr, wrap: wrap, title: h, msg: p };
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
    // Exclude engine-injected empty rows so they never get filtered/sorted/counted/exported.
    return Array.prototype.filter.call(tbody.children, function (r) {
      return r.tagName === "TR" && !(r.classList && r.classList.contains("rmc-tbl-empty-row"));
    });
  }
  function cellText(cell) { return (cell.textContent || "").replace(/\s+/g, " ").trim(); }

  function normalizeDensity(raw, fallback) {
    var key = String(raw || "").toLowerCase().trim();
    if (DENSITY_ALIASES[key]) { return DENSITY_ALIASES[key]; }
    return DENSITIES.indexOf(fallback) !== -1 ? fallback : "comfortable";
  }

  function applyDensity(table, raw) {
    var density = normalizeDensity(raw, cfg.density);
    table.setAttribute("data-density", density);
    DENSITY_CLASSES.forEach(function (cls) { table.classList.remove(cls); });
    table.classList.add("table-density-" + density);
    return density;
  }

  function resolveInitialDensity(table, prefs) {
    if (prefs && DENSITIES.indexOf(prefs.density) !== -1) { return prefs.density; }
    var existing = table.getAttribute("data-density");
    if (existing) { return normalizeDensity(existing, cfg.density); }
    return normalizeDensity(cfg.density, "comfortable");
  }

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

    // density (per-user pref over cascade default; preserve condensed/expanded markup)
    var density = applyDensity(table, resolveInitialDensity(table, prefs));
    prefs.density = density;

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
    var filterEmpty = null;
    function toggleFilterEmpty(on, displayTerm) {
      if (!(emptyCfg.intelligence && emptyCfg.table_filter)) { return; }
      var tbody = table.querySelector("tbody");
      if (!tbody) { return; }
      if (on) {
        if (!filterEmpty) {
          filterEmpty = makeEmptyRow(ncols, "filter");
          filterEmpty.msg.textContent = "Nothing on this page matches your filter.";
          filterEmpty.title.appendChild(document.createTextNode("No matches for "));
          var term = document.createElement("span"); term.className = "rmc-empty__term";
          filterEmpty.title.appendChild(term);
          filterEmpty._term = term;
          var act = document.createElement("div"); act.className = "rmc-empty__actions";
          var btn = document.createElement("button");
          btn.type = "button"; btn.className = "btn btn-sm btn-outline-secondary";
          btn.textContent = "Clear filter";
          btn.addEventListener("click", function () {
            if (bar && bar.input) { bar.input.value = ""; }
            state.q = ""; applyFilter();
            if (bar && bar.input) { try { bar.input.focus(); } catch (_) {} }
          });
          act.appendChild(btn); filterEmpty.wrap.appendChild(act);
        }
        filterEmpty._term.textContent = '"' + displayTerm + '"';
        if (filterEmpty.tr.parentNode !== tbody) { tbody.appendChild(filterEmpty.tr); }
        filterEmpty.tr.hidden = false;
      } else if (filterEmpty) {
        filterEmpty.tr.hidden = true;
      }
    }
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
      toggleFilterEmpty(!!needle && shown === 0 && rows.length > 0, state.q.trim());
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

    /* toolbar: density always when intelligence is on; filter/columns/export need enough rows */
    var bar = null;
    var wantExtras = rows.length >= MIN_ROWS_FOR_BAR && (cfg.filter || cfg.columns || cfg.export);
    if (cfg.intelligence) {
      bar = buildBar(table, {
        cfg: cfg,
        density: density,
        heads: heads,
        hidden: hidden,
        showExtras: wantExtras,
        onFilter: function (v) { state.q = v; applyFilter(); },
        onDensity: function (v) {
          density = applyDensity(table, v);
          prefs.density = density;
          setPrefs(key, prefs);
        },
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

    /* data-empty: a list that rendered with zero rows gets a canonical empty
       state instead of a bare, header-only table. */
    if (emptyCfg.intelligence && emptyCfg.table_data && rows.length === 0) {
      var tb = table.querySelector("tbody");
      if (!tb) { tb = document.createElement("tbody"); table.appendChild(tb); }
      if (!tb.querySelector(".rmc-tbl-empty-row")) {
        var de = makeEmptyRow(ncols, "data");
        de.title.textContent = "Nothing here yet";
        de.msg.textContent = "There's no data to show on this page yet.";
        tb.appendChild(de.tr);
      }
    }
  }

  /* ---- toolbar builder (CSP-safe; createElement only) ---- */
  function buildBar(table, opts) {
    var bar = document.createElement("div");
    bar.className = "rmc-tbl-bar";
    bar.setAttribute("role", "toolbar");

    var count = document.createElement("span");
    count.className = "rmc-tbl-bar__count";
    count.setAttribute("role", "status");
    count.setAttribute("aria-live", "polite");

    var showExtras = opts.showExtras !== false;
    if (showExtras && opts.cfg.filter) {
      var fwrap = document.createElement("div");
      fwrap.className = "rmc-tbl-bar__filter";
      var input = document.createElement("input");
      input.type = "search";
      input.className = "rmc-tbl-bar__input";
      // Sentinel so the form engine doesn't mistake this injected filter for a
      // real search form and skip enhancing a host form it may land inside.
      input.setAttribute("data-rmc-tbl-filter", "1");
      input.setAttribute("placeholder", "Filter these results…");
      input.setAttribute("aria-label", "Filter the rows on this page");
      var debounce;
      input.addEventListener("input", function () {
        clearTimeout(debounce);
        debounce = setTimeout(function () { opts.onFilter(input.value || ""); }, 90);
      });
      // If this filter ever lands inside a <form>, Enter must not submit it.
      input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); } });
      fwrap.appendChild(input);
      bar.appendChild(fwrap);
    }
    bar.appendChild(count);

    // density segmented control — always present when the bar is built
    var seg = document.createElement("div");
    seg.className = "rmc-tbl-seg";
    seg.setAttribute("role", "group");
    seg.setAttribute("aria-label", "Row density");
    [["compact", "Compact"], ["comfortable", "Cozy"], ["spacious", "Roomy"]].forEach(function (d) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "rmc-tbl-seg__btn";
      b.textContent = d[1];
      b.setAttribute("data-density", d[0]);
      b.setAttribute("aria-pressed", d[0] === opts.density ? "true" : "false");
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(seg.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        opts.onDensity(d[0]);
      });
      seg.appendChild(b);
    });
    bar.appendChild(seg);

    // columns popover
    if (showExtras && opts.cfg.columns && opts.heads.length) {
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
    if (showExtras && opts.cfg.export) {
      var csv = document.createElement("button");
      csv.type = "button";
      csv.className = "rmc-tbl-gear";
      csv.textContent = "⤓ CSV";
      csv.addEventListener("click", opts.onExport);
      bar.appendChild(csv);
    }

    var anchor = table.closest(".table-responsive") || table;
    if (anchor.parentNode) { anchor.parentNode.insertBefore(bar, anchor); }
    return { el: bar, count: count, input: bar.querySelector(".rmc-tbl-bar__input") };
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
