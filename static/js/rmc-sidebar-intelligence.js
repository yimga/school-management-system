/* rmc-sidebar-intelligence.js — shared sidebar intelligence engine.
 *
 * ONE brain, every skin. Progressive enhancement that attaches to any sidebar
 * carrying `data-rmc-smart-sidebar="1"`, on BOTH surfaces:
 *   - operator control plane: <details.cp-sidebar__group> / <a.cp-sidebar__item>
 *     (data-shell-nav-family="control-plane")
 *   - tenant portal: flat <div.sidebar-section-title> / <a.nav-link.nav-pill>
 *     (data-shell-nav-family="portal")
 *
 * Capabilities (Phase 1 of the intelligent-sidebar initiative):
 *   1. Type-to-filter   — instant fuzzy filter; empty groups fold away.
 *   2. Adaptive "Frequent" band — surfaces the items this user actually opens.
 *   3. Keyboard         — "/" focuses the filter, ↑/↓ walk results, ↵ navigates.
 *   4. Density          — compact / comfortable / spacious, per-user persisted.
 *
 * No external deps. CSP-safe: never assigns innerHTML from user/runtime data —
 * highlights are built with createElement + textContent. If JS is disabled the
 * sidebar renders exactly as the server produced it. Config flows from the
 * `SITE` cascade via data-attributes on the root nav (no migration needed).
 */
(function () {
  "use strict";
  if (window.__rmcSidebarIntel) return;
  window.__rmcSidebarIntel = true;

  var USAGE_KEY = "rmcSidebarUsage:v1";
  var DENSITY_KEY = "rmcSidebarDensity:v1";
  var MIN_ITEMS_FOR_FILTER = 8; // tiny sidebars don't need a filter
  var FREQUENT_MAX = 4;
  var FREQUENT_MIN_HITS = 2;
  var DENSITIES = ["compact", "comfortable", "spacious"];

  function readJSON(key) {
    try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { return {}; }
  }
  function writeJSON(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* private mode */ }
  }

  function family(root) {
    return root.getAttribute("data-shell-nav-family") || "portal";
  }
  function attrOn(root, name) {
    // treat anything that isn't an explicit "0" as on (cascade default = on)
    var v = root.getAttribute(name);
    return v !== "0" && v !== "false";
  }

  // ── per-surface adapter ────────────────────────────────────────────────
  function adapter(root) {
    if (family(root) === "control-plane") {
      return {
        kind: "details",
        itemSel: "a.cp-sidebar__item",
        labelEl: function (a) { return a.querySelector(".cp-nav-label"); },
        row: function (a) { return a; },
        groups: function () {
          return [].slice.call(root.querySelectorAll("details.cp-sidebar__group, .cp-sidebar__group"))
            .map(function (g) {
              return { el: g, items: [].slice.call(g.querySelectorAll("a.cp-sidebar__item")) };
            });
        }
      };
    }
    return {
      kind: "flat",
      itemSel: "a.nav-link.nav-pill, a.nav-link",
      labelEl: function (a) { return null; }, // portal label is mixed with the icon span
      row: function (a) { return a.closest(".sidebar-nav-item-wrapper") || a; },
      groups: null
    };
  }

  function items(root, ad) {
    return [].slice.call(root.querySelectorAll(ad.itemSel))
      .filter(function (a) { return !a.classList.contains("rmc-sb-frequent__item"); });
  }
  function itemId(a) {
    return a.getAttribute("data-cp-primary-id") ||
      a.getAttribute("data-sidebar-id") ||
      a.getAttribute("data-rmc-unified-nav-id") ||
      a.getAttribute("href") || "";
  }
  function itemLabel(a, ad) {
    var lblEl = ad.labelEl(a);
    if (lblEl) return (lblEl.textContent || "").trim();
    return (a.textContent || "").replace(/\s+/g, " ").trim();
  }
  function itemIcon(a) {
    var i = a.querySelector("i.bi");
    return i ? i.className : "bi bi-circle";
  }

  // ── 1. type-to-filter ──────────────────────────────────────────────────
  function highlight(lblEl, q) {
    if (!lblEl) return;
    var raw = lblEl.getAttribute("data-rmc-raw");
    if (raw === null) { raw = lblEl.textContent; lblEl.setAttribute("data-rmc-raw", raw); }
    var idx = q ? raw.toLowerCase().indexOf(q) : -1;
    if (idx < 0) { lblEl.textContent = raw; return; }
    lblEl.textContent = "";
    lblEl.appendChild(document.createTextNode(raw.slice(0, idx)));
    var mk = document.createElement("mark");
    mk.className = "rmc-sb-mark";
    mk.textContent = raw.slice(idx, idx + q.length);
    lblEl.appendChild(mk);
    lblEl.appendChild(document.createTextNode(raw.slice(idx + q.length)));
  }

  function buildFilterBar(root, ad, state) {
    var bar = document.createElement("div");
    bar.className = "rmc-sb-filter";
    var field = document.createElement("div");
    field.className = "rmc-sb-filter__field";
    var input = document.createElement("input");
    input.type = "search";
    input.className = "rmc-sb-filter__input";
    input.setAttribute("aria-label", "Filter navigation");
    input.placeholder = "Filter…";
    input.autocomplete = "off"; input.spellcheck = false;
    var hint = document.createElement("kbd");
    hint.className = "rmc-sb-filter__hint";
    hint.textContent = "/";
    var density = document.createElement("button");
    density.type = "button";
    density.className = "rmc-sb-filter__density";
    density.setAttribute("aria-label", "Cycle sidebar density");
    density.title = "Density";
    density.textContent = "≡";
    field.appendChild(input); field.appendChild(hint);
    bar.appendChild(field); bar.appendChild(density);

    density.addEventListener("click", function () {
      var cur = root.getAttribute("data-rmc-density") || "comfortable";
      var next = DENSITIES[(DENSITIES.indexOf(cur) + 1) % DENSITIES.length];
      root.setAttribute("data-rmc-density", next);
      writeJSON(DENSITY_KEY, { d: next });
    });

    function apply() {
      var q = input.value.trim().toLowerCase();
      var any = false;
      state.items.forEach(function (it) {
        var hit = !q || it.label.indexOf(q) >= 0;
        ad.row(it.a).classList.toggle("rmc-sb-out", !hit);
        highlight(ad.labelEl(it.a), q);
        if (hit) any = true;
      });
      foldGroups(root, ad, q);
      root.classList.toggle("rmc-sb-no-results", !!q && !any);
      state.cursor = -1; paintCursor(state);
    }
    input.addEventListener("input", apply);
    input.addEventListener("keydown", function (e) {
      var vis = visibleItems(state);
      if (e.key === "ArrowDown") { e.preventDefault(); state.cursor = Math.min(state.cursor + 1, vis.length - 1); paintCursor(state, vis); }
      else if (e.key === "ArrowUp") { e.preventDefault(); state.cursor = Math.max(state.cursor - 1, 0); paintCursor(state, vis); }
      else if (e.key === "Enter" && state.cursor >= 0 && vis[state.cursor]) { e.preventDefault(); vis[state.cursor].a.click(); }
      else if (e.key === "Escape") { input.value = ""; apply(); input.blur(); }
    });
    state.input = input;
    return bar;
  }

  function foldGroups(root, ad, q) {
    if (ad.kind === "details") {
      ad.groups().forEach(function (g) {
        var vis = g.items.some(function (a) { return !ad.row(a).classList.contains("rmc-sb-out"); });
        g.el.classList.toggle("rmc-sb-group-out", !vis);
        if (q && vis && "open" in g.el) {
          if (!g.el.hasAttribute("data-rmc-sb-was-open")) {
            g.el.setAttribute("data-rmc-sb-was-open", g.el.open ? "1" : "0");
          }
          g.el.open = true;
        } else if (!q && g.el.hasAttribute("data-rmc-sb-was-open")) {
          g.el.open = g.el.getAttribute("data-rmc-sb-was-open") === "1";
          g.el.removeAttribute("data-rmc-sb-was-open");
        }
      });
      return;
    }
    // flat (portal): hide a section title when every item under it is filtered out
    var title = null, anyVis = false;
    [].slice.call(root.children).forEach(function (node) {
      if (node.classList && node.classList.contains("sidebar-section-title")) {
        if (title) title.classList.toggle("rmc-sb-out", !anyVis);
        title = node; anyVis = false;
      } else {
        var link = node.matches && node.matches("a.nav-link") ? node : (node.querySelector ? node.querySelector("a.nav-link") : null);
        if (link && !ad.row(link).classList.contains("rmc-sb-out")) anyVis = true;
      }
    });
    if (title) title.classList.toggle("rmc-sb-out", !anyVis);
  }

  function visibleItems(state) {
    return state.items.filter(function (it) { return !state.adRow(it.a).classList.contains("rmc-sb-out"); });
  }
  function paintCursor(state, vis) {
    vis = vis || visibleItems(state);
    state.items.forEach(function (it) { it.a.classList.remove("rmc-sb-cursor"); });
    if (state.cursor >= 0 && vis[state.cursor]) {
      vis[state.cursor].a.classList.add("rmc-sb-cursor");
      vis[state.cursor].a.scrollIntoView({ block: "nearest" });
    }
  }

  // ── 2. adaptive "Frequent" band ─────────────────────────────────────────
  function buildFrequent(root, ad, state) {
    var usage = readJSON(USAGE_KEY);
    var fam = family(root);
    var scored = state.items
      .map(function (it) { return { it: it, hits: usage[fam + "::" + it.id] || 0 }; })
      .filter(function (s) { return s.hits >= FREQUENT_MIN_HITS; })
      .sort(function (a, b) { return b.hits - a.hits; })
      .slice(0, FREQUENT_MAX);
    if (!scored.length) return null;
    var band = document.createElement("div");
    band.className = "rmc-sb-frequent";
    var head = document.createElement("div");
    head.className = "rmc-sb-frequent__head";
    head.textContent = "Frequent";
    band.appendChild(head);
    scored.forEach(function (s) {
      var a = document.createElement("a");
      a.className = "rmc-sb-frequent__item";
      a.href = s.it.a.getAttribute("href") || "#";
      var i = document.createElement("i");
      i.className = itemIcon(s.it.a); i.setAttribute("aria-hidden", "true");
      var lbl = document.createElement("span");
      lbl.className = "rmc-sb-frequent__label"; lbl.textContent = s.it.label_raw;
      var tag = document.createElement("span");
      tag.className = "rmc-sb-frequent__tag"; tag.textContent = "★"; tag.title = "Used often";
      a.appendChild(i); a.appendChild(lbl); a.appendChild(tag);
      band.appendChild(a);
    });
    return band;
  }

  function trackClicks(root) {
    var fam = family(root);
    root.addEventListener("click", function (e) {
      var a = e.target.closest("a[href]");
      if (!a) return;
      if (a.classList.contains("rmc-sb-frequent__item")) return; // clone already maps to id below via href? skip double
      var id = itemId(a);
      if (!id) return;
      var usage = readJSON(USAGE_KEY);
      var k = fam + "::" + id;
      usage[k] = (usage[k] || 0) + 1;
      writeJSON(USAGE_KEY, usage);
    }, true);
  }

  // ── density (config default + per-user override) ────────────────────────
  function applyDensity(root) {
    var override = readJSON(DENSITY_KEY).d;
    var dflt = root.getAttribute("data-rmc-sidebar-density") || "comfortable";
    var val = DENSITIES.indexOf(override) >= 0 ? override : dflt;
    root.setAttribute("data-rmc-density", val);
  }

  // ── init one sidebar ────────────────────────────────────────────────────
  function init(root) {
    if (root.__rmcIntel) return;
    root.__rmcIntel = true;
    try {
      var ad = adapter(root);
      applyDensity(root);
      trackClicks(root);

      var list = items(root, ad).map(function (a) {
        var raw = itemLabel(a, ad);
        return { a: a, id: itemId(a), label: raw.toLowerCase(), label_raw: raw };
      });
      var state = { items: list, cursor: -1, adRow: ad.row };

      // adaptive band first (top of nav), then filter bar above it
      if (attrOn(root, "data-rmc-sidebar-adaptive")) {
        var band = buildFrequent(root, ad, state);
        if (band) root.insertBefore(band, root.firstChild);
      }
      if (attrOn(root, "data-rmc-sidebar-search") && list.length >= MIN_ITEMS_FOR_FILTER) {
        var bar = buildFilterBar(root, ad, state);
        root.insertBefore(bar, root.firstChild);
        root.classList.add("rmc-sb-has-filter");
      }
    } catch (err) {
      // never break the sidebar — degrade to the server-rendered list
      if (window.console && console.warn) console.warn("rmc-sidebar-intelligence:", err);
    }
  }

  // global "/" focuses the nearest smart-sidebar filter (when not typing elsewhere)
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
    var el = document.activeElement;
    if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
    var input = document.querySelector('[data-rmc-smart-sidebar="1"] .rmc-sb-filter__input');
    if (input) { e.preventDefault(); input.focus(); }
  });

  function boot() {
    [].slice.call(document.querySelectorAll('[data-rmc-smart-sidebar="1"]')).forEach(init);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
