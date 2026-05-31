/**
 * v4.01.03 — assist dock g-chord → chip click bridge.
 *
 * Closes the "advertised-but-unbound" gap surfaced by the keyboard
 * shortcut audit. The assist dock chips publish `aria-keyshortcuts`
 * via `default_slots.py` / `power_chips.py`, but the actual keydown
 * listener that maps the chord to a chip click did not exist. AT
 * users pressing the documented chord got nothing — that's the
 * regression this bridge prevents.
 *
 * Contract:
 *   - Listens for `g` then a second key inside a 1200ms window.
 *   - Resolves the second key against `[data-rmc-assist-shortcut]`
 *     attributes the dock paints on its rendered chips.
 *   - Programmatically clicks the chip's button — the dock's own
 *     panel-open / external-anchor logic does the rest.
 *   - Never fires on control-plane surfaces — `_pages/control_plane_base-1.js`
 *     owns the g-chord ladder there (g d / g c / g t / g s / g p ...).
 *   - Never fires while typing into an input / textarea / contenteditable.
 *   - Skipped chords (overlap with control-plane g-prefix, or chip
 *     doesn't always render) are stripped at the source rather than
 *     handled here — see `default_slots.py` / `power_chips.py`.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var G_WINDOW_MS = 1200;
  var gPending = false;
  var gTimeout = null;

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function getSurface() {
    if (window.RMCShortcuts && typeof window.RMCShortcuts.getSurface === "function") {
      return window.RMCShortcuts.getSurface();
    }
    return (document.documentElement.getAttribute("data-rmc-premium-shell") || "tenant").toLowerCase();
  }

  function findChipForSecondKey(secondKey) {
    var chord = "g " + secondKey;
    var nodes = document.querySelectorAll("[data-rmc-assist-shortcut]");
    for (var i = 0; i < nodes.length; i++) {
      var attr = (nodes[i].getAttribute("data-rmc-assist-shortcut") || "").toLowerCase();
      if (attr === chord) return nodes[i];
    }
    return null;
  }

  function armG() {
    gPending = true;
    clearTimeout(gTimeout);
    gTimeout = setTimeout(function () { gPending = false; }, G_WINDOW_MS);
  }

  function disarmG() {
    gPending = false;
    clearTimeout(gTimeout);
  }

  document.addEventListener("keydown", function (e) {
    if (e.defaultPrevented) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (isTypingTarget(e.target)) return;

    // Control plane has its own g-chord owner; let it handle.
    if (getSurface() === "control-plane") return;

    // First key of the chord.
    if (e.key === "g" || e.key === "G") {
      // Don't preventDefault — `rmc-shortcuts-runtime.js` and
      // `rmc-workflow-progress.js` also arm their own g-state from the
      // same event. We piggy-back; the runtime only matches g h / g n / g c
      // and workflow only matches g w, so collisions are safe.
      armG();
      return;
    }

    // Second key of the chord.
    if (!gPending || !e.key || e.key.length !== 1) return;

    var second = e.key.toLowerCase();
    var chip = findChipForSecondKey(second);
    if (!chip) return;

    e.preventDefault();
    disarmG();
    // Anchor chips navigate; button chips open dock panels. Both honor click.
    if (typeof chip.click === "function") chip.click();
  });
})();
