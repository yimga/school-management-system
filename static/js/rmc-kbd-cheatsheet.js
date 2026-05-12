/**
 * Keyboard shortcut cheat sheet — Linear-style `?` overlay.
 *
 * Press `?` (Shift+/) anywhere outside an input/textarea to open. Press
 * Escape to close. Renders as a centered modal with grouped shortcuts.
 *
 * Shortcut data is read from the `window.RMCShortcuts` registry. Each entry:
 *   { keys: "⌘K" | ["⌘", "K"], label: "Open command palette", group: "Navigation" }
 *
 * Other modules can register their own shortcuts via
 *   window.RMCShortcuts.register({ keys, label, group });
 * before this script mounts. Order in the registry = display order within a
 * group. Group order is fixed: Navigation, Actions, View, Help.
 *
 * Honors prefers-reduced-motion (instant open instead of slide).
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var GROUPS = ["Navigation", "Actions", "View", "Help"];
  var DEFAULTS = [
    { keys: ["⌘", "K"], label: "Open command palette", group: "Navigation" },
    { keys: ["?"],      label: "Show this cheat sheet", group: "Help" },
    { keys: ["Esc"],    label: "Close any dialog / palette", group: "Navigation" },
    { keys: ["/"],      label: "Focus the search field (if present)", group: "Navigation" },
    { keys: ["G", "H"], label: "Go to home / dashboard", group: "Navigation" },
    { keys: ["G", "N"], label: "Go to notifications", group: "Navigation" },
    { keys: ["G", "C"], label: "Go to configure", group: "Navigation" },
  ];

  var registry = DEFAULTS.slice();
  window.RMCShortcuts = window.RMCShortcuts || {};
  window.RMCShortcuts.register = function (entry) {
    if (!entry || !entry.keys || !entry.label) return;
    registry.push(entry);
  };
  window.RMCShortcuts.all = function () { return registry.slice(); };

  var dialog = null;
  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "rmc-kbd-cheatsheet rmc-sheet";
    dialog.setAttribute("aria-label", "Keyboard shortcuts");
    dialog.innerHTML = ""
      + '<div class="rmc-sheet__handle" aria-hidden="true"></div>'
      + '<header class="rmc-sheet__header">'
      +   '<h3 class="rmc-sheet__title">Keyboard shortcuts</h3>'
      +   '<button class="rmc-sheet__close" type="button" aria-label="Close" data-rmc-sheet-close>&times;</button>'
      + '</header>'
      + '<div class="rmc-sheet__body rmc-kbd-cheatsheet__body" data-rmc-kbd-body></div>';
    document.body.appendChild(dialog);
    /* Close button. */
    dialog.querySelector("[data-rmc-sheet-close]").addEventListener("click", function () { dialog.close(); });
    /* Click outside the dialog content closes (works with showModal()). */
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) dialog.close();
    });
    return dialog;
  }

  function render() {
    var body = dialog.querySelector("[data-rmc-kbd-body]");
    body.textContent = "";
    var grouped = {};
    for (var i = 0; i < registry.length; i++) {
      var e = registry[i];
      var g = e.group || "Help";
      (grouped[g] = grouped[g] || []).push(e);
    }
    /* Unknown groups (registered by other modules) appended after the known set. */
    var allGroups = GROUPS.slice();
    Object.keys(grouped).forEach(function (g) { if (allGroups.indexOf(g) < 0) allGroups.push(g); });
    for (var gi = 0; gi < allGroups.length; gi++) {
      var groupName = allGroups[gi];
      if (!grouped[groupName] || !grouped[groupName].length) continue;
      var section = document.createElement("section");
      section.className = "rmc-kbd-cheatsheet__group";
      var h = document.createElement("h4");
      h.className = "rmc-kbd-cheatsheet__group-title";
      h.textContent = groupName;
      section.appendChild(h);
      var ul = document.createElement("ul");
      ul.className = "rmc-kbd-cheatsheet__list";
      for (var k = 0; k < grouped[groupName].length; k++) {
        var entry = grouped[groupName][k];
        var li = document.createElement("li");
        li.className = "rmc-kbd-cheatsheet__row";
        var label = document.createElement("span");
        label.className = "rmc-kbd-cheatsheet__label";
        label.textContent = entry.label;
        var keys = document.createElement("span");
        keys.className = "rmc-kbd-cheatsheet__keys";
        var keyList = Array.isArray(entry.keys) ? entry.keys : [entry.keys];
        for (var ki = 0; ki < keyList.length; ki++) {
          if (ki > 0) {
            var plus = document.createElement("span");
            plus.className = "rmc-kbd-cheatsheet__plus";
            plus.textContent = "then";
            keys.appendChild(plus);
          }
          var kbd = document.createElement("kbd");
          kbd.className = "rmc-kbd";
          kbd.textContent = keyList[ki];
          keys.appendChild(kbd);
        }
        li.appendChild(label);
        li.appendChild(keys);
        ul.appendChild(li);
      }
      section.appendChild(ul);
      body.appendChild(section);
    }
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
    render();
    if (typeof dialog.showModal === "function") {
      try { dialog.showModal(); }
      catch (_) { /* already open */ }
    } else {
      dialog.setAttribute("open", "");
    }
  }

  document.addEventListener("keydown", function (e) {
    /* `?` = Shift+/ on most keyboards. */
    if (e.key !== "?" && !(e.key === "/" && e.shiftKey)) return;
    if (isTypingTarget(e.target)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    e.preventDefault();
    open();
  });

  /* Public API so other modules / templates can open the cheat sheet. */
  window.RMCShortcuts.open = open;
})();
