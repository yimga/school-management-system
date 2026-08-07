/**
 * Admin OS v15 Waves 2–4 — I1–I5, I7–I8
 * Selection gravity, dirty save pulse, keymap, row peek, section radar,
 * focus mode, pin & recent.
 */
(function () {
  "use strict";

  var FOCUS_KEY = "rmc-admin-focus-mode";
  var PINS_KEY = "rmc-admin-pins";
  var RECENT_KEY = "rmc-admin-recent";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function hostScope() {
    var ws = document.querySelector("[data-rmc-admin-workspace-scope]");
    if (ws) return ws.getAttribute("data-rmc-admin-workspace-scope") || "tenant";
    return document.body.classList.contains("admin-manager-shell") ? "operator" : "tenant";
  }

  function archetype() {
    var el = document.querySelector("[data-rmc-admin-archetype]");
    return el ? el.getAttribute("data-rmc-admin-archetype") || "discover" : "discover";
  }

  function storageGet(key) {
    try {
      return localStorage.getItem(key + ":" + hostScope());
    } catch (_e) {
      return null;
    }
  }

  function storageSet(key, val) {
    try {
      localStorage.setItem(key + ":" + hostScope(), val);
    } catch (_e) {
      /* ignore */
    }
  }

  function storageJsonGet(key, fallback) {
    var raw = storageGet(key);
    if (!raw) return fallback;
    try {
      return JSON.parse(raw);
    } catch (_e) {
      return fallback;
    }
  }

  function storageJsonSet(key, val) {
    storageSet(key, JSON.stringify(val));
  }

  /* ── Shared sheet primitive (keymap, peek) ── */
  var openSheetId = null;

  function ensureSheet(id, title) {
    var sheet = document.getElementById(id);
    if (sheet) return sheet;
    sheet = document.createElement("aside");
    sheet.id = id;
    sheet.className = "rmc-admin-os-sheet";
    sheet.setAttribute("role", "dialog");
    sheet.setAttribute("aria-modal", "true");
    sheet.setAttribute("hidden", "");
    sheet.innerHTML =
      '<div class="rmc-admin-os-sheet__backdrop" data-rmc-admin-sheet-close="1"></div>' +
      '<div class="rmc-admin-os-sheet__panel">' +
      '<header class="rmc-admin-os-sheet__head">' +
      '<strong class="rmc-admin-os-sheet__title"></strong>' +
      '<button type="button" class="rmc-admin-os-sheet__close" data-rmc-admin-sheet-close="1" aria-label="Close">×</button>' +
      "</header>" +
      '<div class="rmc-admin-os-sheet__body"></div>' +
      "</div>";
    document.body.appendChild(sheet);
    if (title) sheet.querySelector(".rmc-admin-os-sheet__title").textContent = title;
    sheet.addEventListener("click", function (ev) {
      if (ev.target.closest("[data-rmc-admin-sheet-close]")) closeSheet(id);
    });
    return sheet;
  }

  function openSheet(id, title, bodyHtml) {
    var sheet = ensureSheet(id, title);
    sheet.querySelector(".rmc-admin-os-sheet__title").textContent = title || "";
    sheet.querySelector(".rmc-admin-os-sheet__body").innerHTML = bodyHtml || "";
    sheet.removeAttribute("hidden");
    openSheetId = id;
    document.documentElement.setAttribute("data-rmc-admin-sheet-open", "1");
    var closeBtn = sheet.querySelector(".rmc-admin-os-sheet__close");
    if (closeBtn) closeBtn.focus();
  }

  function closeSheet(id) {
    var sid = id || openSheetId;
    if (!sid) return;
    var sheet = document.getElementById(sid);
    if (sheet) sheet.setAttribute("hidden", "");
    if (openSheetId === sid) openSheetId = null;
    if (!document.querySelector(".rmc-admin-os-sheet:not([hidden])")) {
      document.documentElement.removeAttribute("data-rmc-admin-sheet-open");
    }
  }

  function closeAnySheet() {
    if (openSheetId) closeSheet(openSheetId);
  }

  function isSheetOpen() {
    return !!openSheetId;
  }

  /* ── I8 Page keymap ── */
  var KEYMAP_SHORTCUTS = {
    discover: [
      { keys: "⌘K", desc: "Command palette" },
      { keys: "/", desc: "Focus catalog search" },
      { keys: "Esc", desc: "Clear search" },
    ],
    scan: [
      { keys: "⌘K", desc: "Command palette" },
      { keys: "?", desc: "This keymap" },
      { keys: "Space", desc: "Peek focused row" },
      { keys: "Enter", desc: "Open peeked record" },
      { keys: "Esc", desc: "Clear selection / close sheet" },
    ],
    edit: [
      { keys: "⌘K", desc: "Command palette" },
      { keys: "?", desc: "This keymap" },
      { keys: "⌘.", desc: "Toggle focus mode" },
      { keys: "⌘S", desc: "Save" },
      { keys: "Esc", desc: "Exit focus / close sheet" },
    ],
    dossier: [
      { keys: "⌘K", desc: "Command palette" },
      { keys: "?", desc: "This keymap" },
      { keys: "Esc", desc: "Close sheet" },
    ],
    audit: [
      { keys: "⌘K", desc: "Command palette" },
      { keys: "?", desc: "This keymap" },
    ],
    decide: [
      { keys: "Esc", desc: "Cancel / back" },
    ],
  };

  function renderKeymapHtml() {
    var arch = archetype();
    var rows = KEYMAP_SHORTCUTS[arch] || KEYMAP_SHORTCUTS.discover;
    var html = '<ul class="rmc-admin-keymap-list">';
    rows.forEach(function (row) {
      html +=
        '<li><kbd class="rmc-admin-keymap-kbd">' +
        row.keys +
        "</kbd><span>" +
        row.desc +
        "</span></li>";
    });
    html += "</ul>";
    return html;
  }

  function initKeymap() {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-rmc-admin-keymap-open]");
      if (!btn) return;
      ev.preventDefault();
      openSheet("rmc-admin-keymap", "Keyboard shortcuts", renderKeymapHtml());
    });
  }

  /* ── I1 Selection gravity (Scan) ── */
  function changelistCheckboxes() {
    var form = document.getElementById("changelist-form");
    if (!form) return [];
    return Array.prototype.slice.call(
      form.querySelectorAll('input.action-select, input[name="_selected_action"]')
    );
  }

  function selectedCount() {
    return changelistCheckboxes().filter(function (cb) {
      return cb.checked;
    }).length;
  }

  function updateRailSelected(n) {
    var rail = document.querySelector("[data-rmc-django-changelist-rail]");
    if (!rail) return;
    var dd = rail.querySelector("[data-rmc-rail-selected-count]");
    if (!dd) {
      var facts = rail.querySelector("[data-rmc-django-rail-facts]");
      if (!facts) return;
      var row = document.createElement("div");
      row.className = "rmc-django-rail-fact";
      row.setAttribute("data-rmc-rail-selected-row", "1");
      row.innerHTML = "<dt>Selected</dt><dd data-rmc-rail-selected-count>0</dd>";
      facts.appendChild(row);
      dd = row.querySelector("[data-rmc-rail-selected-count]");
    }
    if (dd) {
      dd.textContent = String(n);
      var factRow = dd.closest("[data-rmc-rail-selected-row]");
      if (factRow) factRow.style.display = n > 0 ? "" : "none";
    }
  }

  function initSelectionGravity() {
    var band = document.querySelector('[data-rmc-django-command-band="change-list"]');
    var form = document.getElementById("changelist-form");
    if (!band || !form) return;

    var actionsWrap = band.querySelector(".rmc-django-command-band__actions");
    if (!actionsWrap) return;

    var bulkDock = document.createElement("div");
    bulkDock.className = "rmc-admin-bulk-dock";
    bulkDock.setAttribute("data-rmc-admin-bulk-dock", "1");
    bulkDock.setAttribute("hidden", "");
    bulkDock.innerHTML =
      '<span class="rmc-admin-bulk-dock__count" data-rmc-bulk-count>0 selected</span>' +
      '<label class="visually-hidden" for="rmc-bulk-action-clone">Action</label>' +
      '<select id="rmc-bulk-action-clone" class="rmc-admin-bulk-dock__select" data-rmc-bulk-action-clone></select>' +
      '<button type="button" class="rmc-django-band-action rmc-django-band-action--primary" data-rmc-bulk-run="1">Run</button>' +
      '<button type="button" class="rmc-django-band-action" data-rmc-bulk-clear="1">Clear</button>';
    actionsWrap.appendChild(bulkDock);

    var nativeSelect = form.querySelector('select[name="action"]');
    var cloneSelect = bulkDock.querySelector("[data-rmc-bulk-action-clone]");

    function syncActionOptions() {
      if (!nativeSelect || !cloneSelect) return;
      cloneSelect.innerHTML = "";
      Array.prototype.forEach.call(nativeSelect.options, function (opt) {
        var o = document.createElement("option");
        o.value = opt.value;
        o.textContent = opt.textContent;
        if (opt.disabled) o.disabled = true;
        if (opt.selected) o.selected = true;
        cloneSelect.appendChild(o);
      });
    }

    function clearSelection() {
      changelistCheckboxes().forEach(function (cb) {
        cb.checked = false;
      });
      var toggle = document.getElementById("action-toggle");
      if (toggle) toggle.checked = false;
      refreshBulk();
    }

    function refreshBulk() {
      var n = selectedCount();
      updateRailSelected(n);
      if (n > 0) {
        band.classList.add("is-bulk-active");
        bulkDock.removeAttribute("hidden");
        bulkDock.querySelector("[data-rmc-bulk-count]").textContent =
          n === 1 ? "1 selected" : n + " selected";
        syncActionOptions();
      } else {
        band.classList.remove("is-bulk-active");
        bulkDock.setAttribute("hidden", "");
      }
    }

    bulkDock.querySelector("[data-rmc-bulk-run]").addEventListener("click", function () {
      if (!nativeSelect || !cloneSelect) return;
      nativeSelect.value = cloneSelect.value;
      var go =
        form.querySelector('[type="submit"][name="index"]') ||
        form.querySelector('button[type="submit"]');
      if (go) go.click();
    });

    bulkDock.querySelector("[data-rmc-bulk-clear]").addEventListener("click", clearSelection);

    form.addEventListener("change", function (ev) {
      var t = ev.target;
      if (
        t &&
        (t.matches(".action-select") ||
          t.matches('input[name="_selected_action"]') ||
          t.id === "action-toggle")
      ) {
        refreshBulk();
      }
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && archetype() === "scan" && !isSheetOpen() && selectedCount() > 0) {
        ev.preventDefault();
        clearSelection();
      }
    });

    refreshBulk();
  }

  /* ── I3 Dirty Save pulse (Edit) ── */
  function fieldLabel(el) {
    var row = el.closest(".form-row, .field-box, .flex");
    if (row) {
      var lbl = row.querySelector("label, .form-label");
      if (lbl) return (lbl.textContent || "").replace(/\s+/g, " ").trim();
    }
    return el.name || el.id || "Field";
  }

  function snapshotForm(form) {
    var snap = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled || el.type === "hidden") return;
      if (el.type === "checkbox" || el.type === "radio") {
        snap[el.name + ":" + (el.value || "")] = el.checked;
      } else if (el.type === "file") {
        snap[el.name] = el.files && el.files.length ? el.files[0].name : "";
      } else {
        snap[el.name] = el.value;
      }
    });
    return snap;
  }

  function changedFields(form, initial) {
    var current = snapshotForm(form);
    var labels = [];
    var seen = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled || el.type === "hidden") return;
      var key =
        el.type === "checkbox" || el.type === "radio"
          ? el.name + ":" + (el.value || "")
          : el.name;
      var changed = initial[key] !== current[key];
      if (changed && !seen[el.name]) {
        seen[el.name] = true;
        labels.push(fieldLabel(el));
      }
    });
    return labels;
  }

  function initDirtySave() {
    var workspace = document.querySelector('[data-rmc-admin-archetype="edit"]');
    if (!workspace) return;
    var form =
      document.getElementById(workspace.querySelector("form") && workspace.querySelector("form").id) ||
      workspace.querySelector("form");
    if (!form) return;

    var split = document.querySelector(".rmc-django-save-split");
    var primaryBtn = split && split.querySelector(".rmc-django-save-split__primary");
    var menu = split && split.querySelector("[data-rmc-save-menu]");
    var saveLabel = primaryBtn ? primaryBtn.textContent.trim() : "Save";
    var dirtySection = null;
    var initial = snapshotForm(form);

    function ensureDirtySection() {
      if (!menu || dirtySection) return;
      dirtySection = document.createElement("div");
      dirtySection.className = "rmc-django-save-menu__dirty";
      dirtySection.setAttribute("data-rmc-save-dirty-section", "1");
      dirtySection.setAttribute("hidden", "");
      dirtySection.innerHTML =
        '<div class="rmc-django-save-menu__dirty-title">Changed fields</div>' +
        '<ul class="rmc-django-save-menu__dirty-list" data-rmc-dirty-field-list></ul>' +
        '<div class="rmc-django-save-menu__sep" role="separator"></div>';
      menu.insertBefore(dirtySection, menu.firstChild);
    }

    function refresh() {
      var labels = changedFields(form, initial);
      var dirty = labels.length > 0;
      if (split) split.classList.toggle("is-dirty", dirty);
      if (primaryBtn) {
        primaryBtn.textContent = dirty
          ? "Save · " + labels.length + (labels.length === 1 ? " field" : " fields")
          : saveLabel;
      }
      ensureDirtySection();
      if (dirtySection) {
        if (dirty) {
          dirtySection.removeAttribute("hidden");
          var list = dirtySection.querySelector("[data-rmc-dirty-field-list]");
          list.innerHTML = labels
            .map(function (l) {
              return "<li>" + l.replace(/</g, "&lt;") + "</li>";
            })
            .join("");
        } else {
          dirtySection.setAttribute("hidden", "");
        }
      }
      var pulseDirty = document.querySelector('[data-rmc-pulse="dirty"]');
      if (pulseDirty) {
        var cleanLbl =
          (document.querySelector("[data-rmc-django-rail-pulse]") &&
            document
              .querySelector("[data-rmc-django-rail-pulse]")
              .getAttribute("data-rmc-pulse-dirty")) ||
          "Unsaved";
        var cleanOk =
          (document.querySelector("[data-rmc-django-rail-pulse]") &&
            document
              .querySelector("[data-rmc-django-rail-pulse]")
              .getAttribute("data-rmc-pulse-clean")) ||
          "Clean";
        pulseDirty.textContent = dirty ? cleanLbl : cleanOk;
        pulseDirty.classList.toggle("is-warn", dirty);
      }
    }

    form.addEventListener("input", refresh);
    form.addEventListener("change", refresh);
    form.addEventListener("submit", function () {
      initial = snapshotForm(form);
      refresh();
    });
    refresh();
  }

  /* ── I2 Row peek sheet (Scan) ── */
  var peekEditUrl = null;

  function rowHeaderLabels(table) {
    var headers = [];
    var ths = table.querySelectorAll("thead th");
    Array.prototype.forEach.call(ths, function (th) {
      if (th.querySelector('input[type="checkbox"]')) {
        headers.push("");
        return;
      }
      var text = (th.textContent || "").replace(/\s+/g, " ").trim();
      headers.push(text || "");
    });
    return headers;
  }

  function rowCellPairs(tr, table) {
    var headers = rowHeaderLabels(table);
    var pairs = [];
    var cells = tr.querySelectorAll("th, td");
    var hi = 0;
    Array.prototype.forEach.call(cells, function (td) {
      var header = headers[hi] || "";
      hi += 1;
      if (td.querySelector('input[type="checkbox"]')) return;
      var text = (td.textContent || "").replace(/\s+/g, " ").trim();
      if (!text) return;
      pairs.push({
        label: header || "Field",
        value: text,
      });
    });
    return pairs;
  }

  function rowEditLink(tr) {
    var link =
      tr.querySelector("th a[href], td.field-__str__ a[href], td a.change-link[href]") ||
      tr.querySelector("td a[href], th a[href]");
    return link;
  }

  function openRowPeek(tr) {
    if (!tr) return;
    var table = tr.closest("table");
    var link = rowEditLink(tr);
    peekEditUrl = link ? link.getAttribute("href") : null;
    var pairs = rowCellPairs(tr, table || document);
    var html = '<dl class="rmc-admin-peek-list">';
    pairs.forEach(function (pair) {
      html +=
        "<dt>" +
        pair.label.replace(/</g, "&lt;") +
        "</dt><dd>" +
        pair.value.replace(/</g, "&lt;") +
        "</dd>";
    });
    html += "</dl>";
    if (peekEditUrl) {
      html +=
        '<a class="rmc-django-band-action rmc-django-band-action--primary rmc-admin-peek-open" href="' +
        peekEditUrl.replace(/"/g, "&quot;") +
        '">Open record</a>';
    }
    openSheet("rmc-admin-peek", "Row peek", html);
    tr.classList.add("is-peek-focused");
  }

  function initRowPeek() {
    var panel = document.querySelector("[data-rmc-admin-row-peek]");
    if (!panel) return;
    var table = panel.querySelector("#result_list") || panel.querySelector("table");
    if (!table) return;

    Array.prototype.forEach.call(table.querySelectorAll("tbody tr"), function (tr) {
      if (tr.getAttribute("data-rmc-peek-wired") === "1") return;
      tr.setAttribute("data-rmc-peek-wired", "1");
      tr.setAttribute("tabindex", "0");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "rmc-admin-row-peek-btn";
      btn.setAttribute("data-rmc-row-peek-btn", "1");
      btn.setAttribute("aria-label", "Peek row");
      btn.textContent = "⧉";
      var firstCell = tr.querySelector("th, td");
      if (firstCell) firstCell.appendChild(btn);
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openRowPeek(tr);
      });
    });

    panel.addEventListener("keydown", function (ev) {
      if (archetype() !== "scan") return;
      var row = ev.target.closest("#result_list tbody tr, table tbody tr");
      if (!row) return;
      if (ev.key === " " || ev.key === "Spacebar") {
        ev.preventDefault();
        openRowPeek(row);
      }
      if (ev.key === "Enter" && isSheetOpen() && openSheetId === "rmc-admin-peek" && peekEditUrl) {
        ev.preventDefault();
        window.location.href = peekEditUrl;
      }
    });
  }

  /* ── I4 Section radar (Edit) ── */
  function initSectionRadar() {
    if (!document.querySelector("[data-rmc-admin-section-radar]")) return;
    var main = document.getElementById("content-main");
    if (!main) return;

    var radar = document.createElement("aside");
    radar.className = "rmc-admin-section-radar";
    radar.setAttribute("aria-label", "Section radar");
    main.appendChild(radar);

    // Top-level sections only: a tabular inline's `.inline-group` wraps an
    // inner `fieldset.module`, so the raw selector matches the same section
    // twice. Drop nodes nested inside another matched node so the dot count
    // matches the "On this page" rail + FORM PULSE (7, not 8).
    var raw = Array.prototype.slice.call(
      main.querySelectorAll("fieldset.module, .inline-group")
    );
    var sections = raw.filter(function (node) {
      return !raw.some(function (other) {
        return other !== node && other.contains(node);
      });
    });
    var dots = [];

    Array.prototype.forEach.call(sections, function (sec, i) {
      if (!sec.id) sec.id = "rmc-radar-sec-" + (i + 1);
      sec.style.scrollMarginTop = "84px";
      var dot = document.createElement("button");
      dot.type = "button";
      dot.className = "rmc-admin-section-radar__dot";
      dot.setAttribute("aria-label", "Section " + (i + 1));
      dot.title = "Section " + (i + 1);
      dot.addEventListener("click", function () {
        sec.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      radar.appendChild(dot);
      dots.push({ dot: dot, sec: sec });
    });

    if (!dots.length) {
      radar.setAttribute("hidden", "");
      return;
    }

    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (e) {
            if (e.isIntersecting) {
              dots.forEach(function (d) {
                d.dot.classList.toggle("is-active", d.sec === e.target);
              });
            }
          });
        },
        { rootMargin: "-35% 0px -55% 0px" }
      );
      dots.forEach(function (d) {
        io.observe(d.sec);
      });
    }
  }

  /* ── I5 Focus mode (Edit) ── */
  function applyFocusMode(on) {
    var ws =
      document.querySelector('[data-rmc-admin-focus-root]') ||
      document.querySelector('[data-rmc-django-workspace="change-form"]');
    if (!ws) return;
    if (on) ws.setAttribute("data-rmc-admin-focus", "1");
    else ws.removeAttribute("data-rmc-admin-focus");
    try {
      sessionStorage.setItem(FOCUS_KEY + ":" + hostScope(), on ? "1" : "0");
    } catch (_e) {
      /* ignore */
    }
  }

  function initFocusMode() {
    var ws = document.querySelector("[data-rmc-admin-focus-root]");
    if (!ws) return;
    var stored = null;
    try {
      stored = sessionStorage.getItem(FOCUS_KEY + ":" + hostScope());
    } catch (_e) {
      stored = null;
    }
    if (stored === "1") applyFocusMode(true);

    document.addEventListener("keydown", function (ev) {
      if (archetype() !== "edit") return;
      var mod = ev.metaKey || ev.ctrlKey;
      if (mod && ev.key === ".") {
        ev.preventDefault();
        var on = !ws.hasAttribute("data-rmc-admin-focus");
        applyFocusMode(on);
      }
      if (ev.key === "Escape" && !isSheetOpen() && ws.hasAttribute("data-rmc-admin-focus")) {
        ev.preventDefault();
        applyFocusMode(false);
      }
    });
  }

  /* ── I7 Pin & recent (Discover) ── */
  function modelKeyFromHref(href) {
    try {
      var u = new URL(href, window.location.origin);
      var m = u.pathname.match(/\/admin\/([^/]+)\/([^/]+)\//);
      if (m) return m[1] + "." + m[2];
    } catch (_e) {
      /* ignore */
    }
    return href;
  }

  function initPinsRecent() {
    var mount = document.querySelector("[data-rmc-admin-pins]");
    if (!mount) return;

    var pins = storageJsonGet(PINS_KEY, []);
    var recent = storageJsonGet(RECENT_KEY, []);

    function seedDefaults() {
      if (pins.length) return;
      var scope = hostScope();
      var catalog = document.querySelector("[data-rmc-admin-catalog-index]");
      if (!catalog) return;
      var want =
        scope === "operator"
          ? ["auth.user", "schools.school", "accounts.user"]
          : ["siteconfig.sitesettings", "people", "accounts.user"];
      var links = catalog.querySelectorAll("a[href*='/admin/']");
      Array.prototype.forEach.call(links, function (a) {
        var key = modelKeyFromHref(a.getAttribute("href"));
        var label = (a.textContent || "").replace(/\s+/g, " ").trim();
        want.forEach(function (w) {
          if (key.indexOf(w) !== -1 || label.toLowerCase().indexOf(w.split(".")[1] || w) !== -1) {
            if (!pins.some(function (p) {
              return p.href === a.getAttribute("href");
            })) {
              pins.push({ href: a.getAttribute("href"), label: label, key: key });
            }
          }
        });
      });
      if (pins.length) storageJsonSet(PINS_KEY, pins);
    }

    function render() {
      mount.innerHTML = "";
      var hasContent = pins.length || recent.length;
      if (!hasContent) {
        mount.setAttribute("hidden", "");
        return;
      }
      mount.removeAttribute("hidden");

      if (pins.length) {
        var pinRow = document.createElement("div");
        pinRow.className = "rmc-admin-pins-row__group";
        pinRow.innerHTML = '<span class="rmc-admin-pins-row__label">Pinned</span>';
        var pinChips = document.createElement("div");
        pinChips.className = "rmc-admin-pins-row__chips";
        pins.forEach(function (p, idx) {
          var chip = document.createElement("a");
          chip.className = "rmc-admin-pin-chip";
          chip.href = p.href;
          chip.textContent = p.label;
          chip.setAttribute("data-rmc-pin-chip", "1");
          var unpin = document.createElement("button");
          unpin.type = "button";
          unpin.className = "rmc-admin-pin-chip__toggle";
          unpin.setAttribute("aria-label", "Unpin");
          unpin.textContent = "×";
          unpin.addEventListener("click", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            pins.splice(idx, 1);
            storageJsonSet(PINS_KEY, pins);
            render();
          });
          chip.appendChild(unpin);
          pinChips.appendChild(chip);
        });
        pinRow.appendChild(pinChips);
        mount.appendChild(pinRow);
      }

      if (recent.length) {
        var recRow = document.createElement("div");
        recRow.className = "rmc-admin-pins-row__group";
        recRow.innerHTML = '<span class="rmc-admin-pins-row__label">Recent</span>';
        var recChips = document.createElement("div");
        recChips.className = "rmc-admin-pins-row__chips";
        recent.slice(0, 8).forEach(function (r) {
          var chip = document.createElement("a");
          chip.className = "rmc-admin-recent-chip";
          chip.href = r.href;
          chip.textContent = r.label;
          recChips.appendChild(chip);
        });
        recRow.appendChild(recChips);
        mount.appendChild(recRow);
      }
    }

    function recordRecent(a) {
      var href = a.getAttribute("href");
      if (!href || href.indexOf("/admin/") === -1) return;
      var label = (a.textContent || "").replace(/\s+/g, " ").trim();
      var key = modelKeyFromHref(href);
      recent = recent.filter(function (r) {
        return r.href !== href;
      });
      recent.unshift({ href: href, label: label, key: key });
      if (recent.length > 12) recent = recent.slice(0, 12);
      storageJsonSet(RECENT_KEY, recent);
      render();
    }

    function togglePin(a) {
      var href = a.getAttribute("href");
      var label = (a.textContent || "").replace(/\s+/g, " ").trim();
      var key = modelKeyFromHref(href);
      var idx = -1;
      pins.forEach(function (p, i) {
        if (p.href === href) idx = i;
      });
      if (idx >= 0) pins.splice(idx, 1);
      else pins.push({ href: href, label: label, key: key });
      storageJsonSet(PINS_KEY, pins);
      render();
    }

    seedDefaults();
    render();

    document.addEventListener("click", function (ev) {
      var card = ev.target.closest(".rmc-admin-catalog-model-card, .cp-catalog-card__items a");
      if (card && card.getAttribute("href")) recordRecent(card);
      var pinBtn = ev.target.closest("[data-rmc-catalog-pin]");
      if (pinBtn) {
        ev.preventDefault();
        var link = pinBtn.closest(".rmc-admin-catalog-model-card");
        if (link) togglePin(link);
      }
    });

    document.querySelectorAll(".rmc-admin-catalog-model-card").forEach(function (card) {
      if (card.querySelector("[data-rmc-catalog-pin]")) return;
      var pin = document.createElement("button");
      pin.type = "button";
      pin.className = "rmc-admin-catalog-pin";
      pin.setAttribute("data-rmc-catalog-pin", "1");
      pin.setAttribute("aria-label", "Pin model");
      pin.textContent = "☆";
      card.appendChild(pin);
    });
  }

  /* ── Global Esc / discover search ── */
  function initGlobalShortcuts() {
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && isSheetOpen()) {
        ev.preventDefault();
        closeAnySheet();
        return;
      }
      if (archetype() === "discover" && ev.key === "/" && !ev.metaKey && !ev.ctrlKey) {
        var tag = (ev.target && ev.target.tagName) || "";
        if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;
        var search = document.querySelector("[data-rmc-admin-catalog-search]");
        if (search) {
          ev.preventDefault();
          search.focus();
        }
      }
    });
  }

  ready(function () {
    initKeymap();
    initSelectionGravity();
    initDirtySave();
    initRowPeek();
    initSectionRadar();
    initFocusMode();
    initPinsRecent();
    initGlobalShortcuts();
    window.setTimeout(initRowPeek, 300);
  });
})();
