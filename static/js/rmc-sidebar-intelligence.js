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
  var PREFS_KEY = "rmcSidebarPrefs:v1"; // per-user {density, adaptive, search}
  var MIN_ITEMS_FOR_FILTER = 6; // tiny sidebars don't need a filter
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
  // Effective boolean for a capability: per-user pref (localStorage) wins over
  // the cascade default emitted on the root (data-rmc-sidebar-<name>).
  function prefBool(root, name) {
    var p = readJSON(PREFS_KEY);
    if (typeof p[name] === "boolean") return p[name];
    return attrOn(root, "data-rmc-sidebar-" + name);
  }

  function usesDetailsGroups(root) {
    return family(root) === "control-plane" || root.getAttribute("data-rmc-cp-sidebar-v8") === "1";
  }

  // ── per-surface adapter ────────────────────────────────────────────────
  function adapter(root) {
    if (usesDetailsGroups(root)) {
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
    // Per-user preferences popover (localStorage) — density + the two capability
    // toggles, layered over the cascade defaults. No backend round-trip.
    var prefsBtn = document.createElement("button");
    prefsBtn.type = "button";
    prefsBtn.className = "rmc-sb-filter__prefs";
    prefsBtn.setAttribute("aria-label", "Sidebar preferences");
    prefsBtn.setAttribute("aria-expanded", "false");
    prefsBtn.title = "Sidebar preferences";
    prefsBtn.textContent = "⚙"; // gear
    var pop = document.createElement("div");
    pop.className = "rmc-sb-prefs";
    pop.hidden = true;

    var dgroup = document.createElement("div");
    dgroup.className = "rmc-sb-prefs__group";
    var dlbl = document.createElement("span");
    dlbl.className = "rmc-sb-prefs__lbl";
    dlbl.textContent = "Density";
    var seg = document.createElement("div");
    seg.className = "rmc-sb-prefs__seg";
    DENSITIES.forEach(function (d) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "rmc-sb-prefs__seg-btn";
      b.setAttribute("data-density", d);
      b.textContent = d.charAt(0).toUpperCase() + d.slice(1);
      b.addEventListener("click", function () {
        root.setAttribute("data-rmc-density", d);
        var p = readJSON(PREFS_KEY); p.density = d; writeJSON(PREFS_KEY, p);
        [].slice.call(seg.children).forEach(function (c) { c.classList.toggle("is-active", c === b); });
      });
      seg.appendChild(b);
    });
    dgroup.appendChild(dlbl); dgroup.appendChild(seg);
    pop.appendChild(dgroup);

    function toggleRow(label, key) {
      var row = document.createElement("label");
      row.className = "rmc-sb-prefs__row";
      var cb = document.createElement("input");
      cb.type = "checkbox"; cb.className = "rmc-sb-prefs__cb";
      var txt = document.createElement("span");
      txt.textContent = label;
      row.appendChild(cb); row.appendChild(txt);
      cb.addEventListener("change", function () {
        var p = readJSON(PREFS_KEY); p[key] = cb.checked; writeJSON(PREFS_KEY, p);
        applyVisibility();
      });
      pop.appendChild(row);
      return cb;
    }
    var adaptiveCb = toggleRow("Adaptive ordering", "adaptive");
    var searchCb = toggleRow("Filter box", "search");

    // Admin-only link to set the SCHOOL DEFAULTS (shown when the server exposes
    // the config URL, i.e. the viewer can manage settings).
    var cfgUrl = root.getAttribute("data-rmc-sidebar-config-url");
    if (cfgUrl) {
      var link = document.createElement("a");
      link.className = "rmc-sb-prefs__link";
      link.href = cfgUrl;
      link.textContent = "School defaults…";
      pop.appendChild(link);
    }

    field.appendChild(input); field.appendChild(hint);
    bar.appendChild(field); bar.appendChild(prefsBtn); bar.appendChild(pop);

    prefsBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      pop.hidden = !pop.hidden;
      prefsBtn.setAttribute("aria-expanded", pop.hidden ? "false" : "true");
    });
    document.addEventListener("click", function (e) {
      if (!pop.hidden && !bar.contains(e.target)) {
        pop.hidden = true; prefsBtn.setAttribute("aria-expanded", "false");
      }
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
    function applyVisibility() {
      var effSearch = prefBool(root, "search");
      var effAdaptive = prefBool(root, "adaptive");
      field.style.display = effSearch ? "" : "none";
      if (!effSearch && input.value) { input.value = ""; apply(); }
      searchCb.checked = effSearch;
      adaptiveCb.checked = effAdaptive;
      var dcur = root.getAttribute("data-rmc-density") || "comfortable";
      [].slice.call(seg.children).forEach(function (c) {
        c.classList.toggle("is-active", c.getAttribute("data-density") === dcur);
      });
      if (state.band) state.band.hidden = !effAdaptive;
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
    state.applyVisibility = applyVisibility;
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
      tag.className = "rmc-sb-frequent__tag"; tag.textContent = "often"; tag.title = "Used often";
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

  // ── active-page marker ───────────────────────────────────────────────────
  // The portal sidebar never marked the current page, so clicking the item for
  // the page you are already on re-landed in place and read as "it just reloaded
  // the same page" (owner complaint). Mark the longest path-prefix match with
  // aria-current="page" so the active item is always visually obvious. The
  // [aria-current="page"] styling already ships in portal-sidebar.css and mirrors
  // the header's tp-primary-nav contract. Fails soft — never breaks the sidebar.
  function markActive(root) {
    try {
      var here = (location.pathname || "/").replace(/\/+$/, "") || "/";
      var links = [].slice.call(root.querySelectorAll("a.nav-link[href], a.cp-sidebar__item[href]"));
      var best = null, bestLen = -1;
      links.forEach(function (a) {
        var href = a.getAttribute("href") || "";
        if (!href || href.charAt(0) === "#") return;
        var path;
        try { path = new URL(href, location.origin).pathname.replace(/\/+$/, "") || "/"; }
        catch (e) { return; }
        if (path === "/") {
          if (here === "/" && bestLen < 0) { best = a; bestLen = 0; }
          return;
        }
        if (here === path || here.indexOf(path + "/") === 0) {
          if (path.length > bestLen) { best = a; bestLen = path.length; }
        }
      });
      links.forEach(function (a) {
        a.classList.remove("cp-sidebar__item--current");
        if (a !== best) a.removeAttribute("aria-current");
      });
      if (best) {
        best.setAttribute("aria-current", "page");
        if (best.classList.contains("cp-sidebar__item")) {
          best.classList.add("cp-sidebar__item--current");
        }
      }
    } catch (err) { /* never break the sidebar over an active marker */ }
  }

  // ── density (config default + per-user override) ────────────────────────
  function applyDensity(root) {
    var pref = readJSON(PREFS_KEY).density || readJSON(DENSITY_KEY).d; // PREFS wins; legacy fallback
    var dflt = root.getAttribute("data-rmc-sidebar-density") || "comfortable";
    var val = DENSITIES.indexOf(pref) >= 0 ? pref : dflt;
    root.setAttribute("data-rmc-density", val);
  }

  // ── 3. live awareness badges ────────────────────────────────────────────
  // Poll a JSON endpoint ({ "badges": {id: count}, "interval": sec }) and keep
  // nav badges current without a reload. Reconciles with any server-rendered
  // badge so tenant items don't double up; operator items (no server badge) get
  // a managed .rmc-sb-livebadge. Fails soft and gives up after repeated errors.
  var SAFE_ID = /^[\w:.\-]+$/;
  function setLiveBadge(root, id, count) {
    id = String(id);
    if (!SAFE_ID.test(id)) return;
    var sel = '[data-cp-primary-id="' + id + '"], [data-sidebar-id="' + id + '"], [data-rmc-unified-nav-id="' + id + '"]';
    [].slice.call(root.querySelectorAll(sel)).forEach(function (a) {
      if (a.classList.contains("rmc-sb-frequent__item")) return;
      var existing = a.querySelector(".badge, .rmc-sb-livebadge");
      if (count > 0) {
        var text = count > 99 ? "99+" : String(count);
        if (existing) { existing.textContent = text; existing.hidden = false; existing.style.display = ""; }
        else {
          var b = document.createElement("span");
          b.className = "rmc-sb-livebadge";
          b.textContent = text;
          a.appendChild(b);
          a.classList.add("rmc-sb-has-livebadge");
        }
      } else if (existing) {
        if (existing.classList.contains("rmc-sb-livebadge")) { existing.remove(); a.classList.remove("rmc-sb-has-livebadge"); }
        else { existing.style.display = "none"; }
      }
    });
  }
  function liveBadges(root) {
    var url = root.getAttribute("data-rmc-badge-poll");
    if (!url) return;
    var fails = 0, timer = null;
    function schedule(ms) { if (timer) clearTimeout(timer); timer = setTimeout(poll, ms); }
    function poll() {
      fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
        .then(function (d) {
          fails = 0;
          var badges = (d && d.badges) || {};
          Object.keys(badges).forEach(function (id) { setLiveBadge(root, id, parseInt(badges[id], 10) || 0); });
          schedule(Math.max(20, parseInt(d && d.interval, 10) || 60) * 1000);
        })
        .catch(function () { fails += 1; if (fails < 3) schedule(60000); });
    }
    poll();
  }

  // ── init one sidebar ────────────────────────────────────────────────────
  function ensureScrollRoot(root) {
    var scrollRoot =
      root.closest(".tp-sidebar-inner") ||
      root.closest(".cp-sidebar-inner") ||
      root.closest("[data-rmc-sidebar-scroll-root]");
    if (!scrollRoot || scrollRoot === root) return;
    scrollRoot.setAttribute("data-rmc-sidebar-scroll-root", "1");
    root.style.overflow = "visible";
    root.style.maxHeight = "none";
  }

  function init(root) {
    if (root.__rmcIntel) return;
    root.__rmcIntel = true;
    try {
      ensureScrollRoot(root);
      var ad = adapter(root);
      applyDensity(root);
      trackClicks(root);
      markActive(root);
      liveBadges(root);

      var list = items(root, ad).map(function (a) {
        var raw = itemLabel(a, ad);
        return { a: a, id: itemId(a), label: raw.toLowerCase(), label_raw: raw };
      });
      var state = { items: list, cursor: -1, adRow: ad.row };

      // Adaptive "Frequent" band — built whenever there's usage history; its
      // visibility follows the effective adaptive pref (user over cascade), so
      // the popover toggle can always show/hide it.
      var band = buildFrequent(root, ad, state);
      if (band) { root.insertBefore(band, root.firstChild); state.band = band; }

      // Filter bar + preferences popover — built whenever the list is long
      // enough; the search field's visibility follows the effective pref.
      if (list.length >= MIN_ITEMS_FOR_FILTER) {
        var bar = buildFilterBar(root, ad, state);
        root.insertBefore(bar, root.firstChild);
        root.classList.add("rmc-sb-has-filter");
        state.applyVisibility();
      } else if (band) {
        band.hidden = !prefBool(root, "adaptive");
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
