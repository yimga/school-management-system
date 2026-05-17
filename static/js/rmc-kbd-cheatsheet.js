/**
 * Platform-wide keyboard shortcuts — Facebook-style multi-column overlay.
 *
 * Triggers: `?` (Shift+/), F1, or user menu → Keyboard shortcuts.
 * Data: window.RMCShortcuts registry (see rmc-shortcuts-registry.js).
 *
 * Features:
 * - Multi-column grouped layout with unavailable shortcuts greyed out
 * - Single-character shortcut toggle (localStorage)
 * - Optional pinned "?" chip in the corner
 * - Unifies cpShowShortcutsHelp with RMCShortcuts.open
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var GROUP_ORDER_KEYS = [
    "group.global",
    "group.search",
    "group.navigation",
    "group.control_plane",
    "group.assistant",
    "group.view",
    "group.inbox",
    "group.gradebook",
    "group.admissions",
    "group.studio",
    "group.finance",
    "group.help",
  ];

  function t(key, fallback) {
    if (window.RMCShortcuts && typeof window.RMCShortcuts.t === "function") {
      return window.RMCShortcuts.t(key, fallback);
    }
    return fallback || "";
  }
  var STORAGE_SINGLE = "rmc-kbd:single-char";
  var STORAGE_PINNED = "rmc-kbd:pinned";
  var isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(navigator.platform || "");

  function getSurface() {
    var el = document.documentElement;
    var shell = (el.getAttribute("data-rmc-premium-shell") || "").toLowerCase();
    if (shell === "control-plane") return "control-plane";
    if (shell === "marketing") return "marketing";
    if (shell === "portal") return "portal";
    var surface = (el.getAttribute("data-surface") || "").toLowerCase();
    if (surface === "control-plane") return "control-plane";
    if (surface === "marketing") return "marketing";
    if (surface === "onboarding") return "onboarding";
    return "tenant";
  }

  function formatKey(key) {
    if (!key) return "";
    var k = String(key);
    if (k === "Ctrl") return isMac ? "⌘" : "Ctrl";
    if (k === "Alt") return isMac ? "⌥" : "Alt";
    if (k === "Shift") return isMac ? "⇧" : "Shift";
    if (k === "Esc") return "Esc";
    if (k === "Enter") return "↵";
    if (k === "ArrowLeft") return "←";
    if (k === "ArrowRight") return "→";
    if (k === "ArrowUp") return "↑";
    if (k === "ArrowDown") return "↓";
    return k;
  }

  function singleCharEnabled() {
    try {
      return localStorage.getItem(STORAGE_SINGLE) !== "0";
    } catch (_) {
      return true;
    }
  }

  function setSingleCharEnabled(on) {
    try {
      localStorage.setItem(STORAGE_SINGLE, on ? "1" : "0");
    } catch (_) {}
  }

  function pinEnabled() {
    try {
      return localStorage.getItem(STORAGE_PINNED) === "1";
    } catch (_) {
      return false;
    }
  }

  function setPinEnabled(on) {
    try {
      localStorage.setItem(STORAGE_PINNED, on ? "1" : "0");
    } catch (_) {}
  }

  function resolveEntryState(entry) {
    var surface = getSurface();
    var surfaces = entry.surfaces;
    var onSurface = !surfaces || !surfaces.length || surfaces.indexOf("*") >= 0 || surfaces.indexOf(surface) >= 0;
    var pages = entry.pages;
    if (pages && pages.length) {
      var page = (window.RMCShortcuts && window.RMCShortcuts.getCurrentPage)
        ? window.RMCShortcuts.getCurrentPage()
        : "";
      if (pages.indexOf(page) < 0 && pages.indexOf("*") < 0) {
        onSurface = false;
      }
    }
    var whenOk = true;
    if (typeof entry.when === "function") {
      try {
        whenOk = !!entry.when();
      } catch (_) {
        whenOk = false;
      }
    }
    if (onSurface && whenOk) return "active";
    if (entry.showUnavailable) return "disabled";
    return "hidden";
  }

  function visibleEntries() {
    var list = (window.RMCShortcuts && window.RMCShortcuts.all) ? window.RMCShortcuts.all() : [];
    var out = [];
    var singleOn = singleCharEnabled();
    unavailableLabel = t("label.unavailable", "Unavailable here");
    for (var i = 0; i < list.length; i++) {
      var e = list[i];
      var state = resolveEntryState(e);
      if (state === "hidden") continue;
      if (!singleOn && e.singleChar) continue;
      out.push({ entry: e, state: state });
    }
    return out;
  }

  var dialog = null;
  var pinBtn = null;

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "rmc-kbd-cheatsheet rmc-kbd-cheatsheet--platform rmc-sheet";
    dialog.setAttribute("aria-label", "All keyboard shortcuts");
    dialog.innerHTML = ""
      + '<div class="rmc-sheet__handle" aria-hidden="true"></div>'
      + '<header class="rmc-sheet__header rmc-kbd-cheatsheet__header">'
      +   '<div class="rmc-kbd-cheatsheet__header-main">'
      +     '<h3 class="rmc-sheet__title">All keyboard shortcuts</h3>'
      +     '<input type="search" class="rmc-kbd-cheatsheet__filter" data-rmc-kbd-filter placeholder="Filter shortcuts" aria-label="Filter shortcuts" autocomplete="off">'
      +   '</div>'
      +   '<button class="rmc-sheet__close" type="button" aria-label="Close" data-rmc-sheet-close>&times;</button>'
      + '</header>'
      + '<div class="rmc-sheet__body rmc-kbd-cheatsheet__grid" data-rmc-kbd-grid></div>'
      + '<footer class="rmc-kbd-cheatsheet__footer">'
      +   '<label class="rmc-kbd-cheatsheet__toggle">'
      +     '<input type="checkbox" data-rmc-kbd-single-char checked>'
      +     '<span>Single-character shortcuts</span>'
      +   '</label>'
      +   '<label class="rmc-kbd-cheatsheet__toggle">'
      +     '<input type="checkbox" data-rmc-kbd-pin>'
      +     '<span>Pin shortcut help to corner</span>'
      +   '</label>'
      + '</footer>';
    document.body.appendChild(dialog);
    dialog.querySelector("[data-rmc-sheet-close]").addEventListener("click", function () {
      dialog.close();
    });
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) dialog.close();
    });
    var singleInput = dialog.querySelector("[data-rmc-kbd-single-char]");
    var pinInput = dialog.querySelector("[data-rmc-kbd-pin]");
    if (singleInput) {
      singleInput.checked = singleCharEnabled();
      singleInput.addEventListener("change", function () {
        setSingleCharEnabled(singleInput.checked);
        render();
      });
    }
    if (pinInput) {
      pinInput.checked = pinEnabled();
      pinInput.addEventListener("change", function () {
        setPinEnabled(pinInput.checked);
        syncPinButton();
      });
    }
    var filterInput = dialog.querySelector("[data-rmc-kbd-filter]");
    if (filterInput) {
      filterInput.addEventListener("input", function () {
        applyFilter(filterInput.value);
      });
    }
    applyDialogI18n();
    return dialog;
  }

  function applyDialogI18n() {
    if (!dialog) return;
    dialog.setAttribute("aria-label", t("title.all_shortcuts", "All keyboard shortcuts"));
    var title = dialog.querySelector(".rmc-sheet__title");
    if (title) title.textContent = t("title.all_shortcuts", "All keyboard shortcuts");
    var filter = dialog.querySelector("[data-rmc-kbd-filter]");
    if (filter) {
      filter.placeholder = t("filter.placeholder", "Filter shortcuts");
      filter.setAttribute("aria-label", t("filter.placeholder", "Filter shortcuts"));
    }
    var toggles = dialog.querySelectorAll(".rmc-kbd-cheatsheet__toggle span");
    if (toggles.length >= 2) {
      toggles[0].textContent = t("toggle.single_char", "Single-character shortcuts");
      toggles[1].textContent = t("toggle.pin", "Pin shortcut help to corner");
    }
    var pin = document.querySelector(".rmc-kbd-cheatsheet__pin");
    if (pin) {
      pin.setAttribute("aria-label", t("title.all_shortcuts", "Keyboard shortcuts"));
      pin.title = t("title.all_shortcuts", "Keyboard shortcuts") + " (?)";
    }
  }

  var filterQuery = "";
  var unavailableLabel = "Unavailable here";

  function applyFilter(query) {
    filterQuery = (query || "").trim().toLowerCase();
    if (!dialog) return;
    var rows = dialog.querySelectorAll(".rmc-kbd-cheatsheet__row");
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var label = (row.getAttribute("data-rmc-kbd-label") || "").toLowerCase();
      var col = row.closest(".rmc-kbd-cheatsheet__column");
      var groupEl = col ? col.querySelector(".rmc-kbd-cheatsheet__group-title") : null;
      var group = groupEl ? (groupEl.textContent || "").toLowerCase() : "";
      var match = !filterQuery || label.indexOf(filterQuery) >= 0 || group.indexOf(filterQuery) >= 0;
      row.hidden = !match;
    }
    var cols = dialog.querySelectorAll(".rmc-kbd-cheatsheet__column");
    for (var c = 0; c < cols.length; c++) {
      var visible = cols[c].querySelector(".rmc-kbd-cheatsheet__row:not([hidden])");
      cols[c].hidden = !visible;
    }
  }

  function renderKeys(container, keyList) {
    for (var ki = 0; ki < keyList.length; ki++) {
      if (ki > 0) {
        var plus = document.createElement("span");
        plus.className = "rmc-kbd-cheatsheet__plus";
        plus.textContent = ki === keyList.length - 1 && keyList.length === 2 ? "then" : "+";
        container.appendChild(plus);
      }
      var kbd = document.createElement("kbd");
      kbd.className = "rmc-kbd";
      kbd.textContent = formatKey(keyList[ki]);
      container.appendChild(kbd);
    }
  }

  function render() {
    ensureDialog();
    var grid = dialog.querySelector("[data-rmc-kbd-grid]");
    grid.textContent = "";
    var grouped = {};
    var rows = visibleEntries();
    var resolveGroupFn = window.RMCShortcuts && window.RMCShortcuts.resolveGroup;
    for (var i = 0; i < rows.length; i++) {
      var entry = rows[i].entry;
      var sortKey = entry.groupKey || entry.group || "group.help";
      if (!grouped[sortKey]) {
        grouped[sortKey] = {
          title: resolveGroupFn ? resolveGroupFn(entry) : (entry.group || "Help"),
          rows: [],
        };
      }
      grouped[sortKey].rows.push(rows[i]);
    }
    var orderedKeys = GROUP_ORDER_KEYS.slice();
    Object.keys(grouped).forEach(function (k) {
      if (orderedKeys.indexOf(k) < 0) orderedKeys.push(k);
    });
    for (var gi = 0; gi < orderedKeys.length; gi++) {
      var sortKey = orderedKeys[gi];
      var bucket = grouped[sortKey];
      if (!bucket || !bucket.rows.length) continue;
      var col = document.createElement("section");
      col.className = "rmc-kbd-cheatsheet__column";
      var h = document.createElement("h4");
      h.className = "rmc-kbd-cheatsheet__group-title";
      h.textContent = bucket.title;
      col.appendChild(h);
      var ul = document.createElement("ul");
      ul.className = "rmc-kbd-cheatsheet__list";
      for (var k = 0; k < bucket.rows.length; k++) {
        var row = bucket.rows[k];
        var entry = row.entry;
        var li = document.createElement("li");
        li.className = "rmc-kbd-cheatsheet__row";
        if (row.state === "disabled") li.classList.add("rmc-kbd-cheatsheet__row--disabled");
        var labelText = window.RMCShortcuts && window.RMCShortcuts.resolveLabel
          ? window.RMCShortcuts.resolveLabel(entry)
          : (entry.label || "");
        var label = document.createElement("span");
        label.className = "rmc-kbd-cheatsheet__label";
        label.textContent = labelText;
        li.setAttribute("data-rmc-kbd-label", labelText);
        var keys = document.createElement("span");
        keys.className = "rmc-kbd-cheatsheet__keys";
        var keyList = Array.isArray(entry.keys) ? entry.keys : [entry.keys];
        renderKeys(keys, keyList);
        li.appendChild(label);
        li.appendChild(keys);
        if (row.state === "disabled") {
          var hint = document.createElement("span");
          hint.className = "rmc-kbd-cheatsheet__unavailable";
          hint.textContent = unavailableLabel;
          li.appendChild(hint);
        }
        ul.appendChild(li);
      }
      col.appendChild(ul);
      grid.appendChild(col);
    }
    var pinEl = dialog.querySelector("[data-rmc-kbd-pin]");
    if (pinEl) pinEl.checked = pinEnabled();
    applyFilter(filterQuery);
    var filterInput = dialog.querySelector("[data-rmc-kbd-filter]");
    if (filterInput && filterInput.value !== filterQuery) filterInput.value = filterQuery;
  }


  function syncPinButton() {
    if (!pinEnabled()) {
      if (pinBtn && pinBtn.parentNode) pinBtn.parentNode.removeChild(pinBtn);
      pinBtn = null;
      return;
    }
    if (pinBtn) return;
    pinBtn = document.createElement("button");
    pinBtn.type = "button";
    pinBtn.className = "rmc-kbd-cheatsheet__pin";
    pinBtn.setAttribute("aria-label", "Keyboard shortcuts");
    pinBtn.title = "Keyboard shortcuts (?)";
    pinBtn.textContent = "?";
    pinBtn.addEventListener("click", function () {
      open();
    });
    document.body.appendChild(pinBtn);
  }

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function open() {
    ensureDialog();
    filterQuery = "";
    var filterInput = dialog.querySelector("[data-rmc-kbd-filter]");
    if (filterInput) filterInput.value = "";
    render();
    if (typeof dialog.showModal === "function") {
      try {
        dialog.showModal();
      } catch (_) {
        /* already open */
      }
    } else {
      dialog.setAttribute("open", "");
    }
  }

  function close() {
    if (dialog && dialog.open) dialog.close();
  }

  window.RMCShortcuts = window.RMCShortcuts || {};
  window.RMCShortcuts.open = open;
  window.RMCShortcuts.close = close;
  window.RMCShortcuts.getSurface = getSurface;
  window.cpShowShortcutsHelp = open;

  document.addEventListener("keydown", function (e) {
    if (e.key === "F1") {
      e.preventDefault();
      open();
      return;
    }
    if (e.key !== "?" && !(e.key === "/" && e.shiftKey)) return;
    if (isTypingTarget(e.target)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    e.preventDefault();
    if (dialog && dialog.open) close();
    else open();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncPinButton);
  } else {
    syncPinButton();
  }
})();
