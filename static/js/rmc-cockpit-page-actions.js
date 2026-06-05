/* rmc-cockpit-page-actions.js — wires the cockpit page-header action buttons.
 *
 *   Export PDF  → if the button carries data-export-url, the anchor navigates
 *                 there (server-side branded PDF). Otherwise we trigger the
 *                 browser print path; the print-v2 stylesheet renders a branded
 *                 PDF when the operator chooses "Save as PDF".
 *   Quick action → opens the platform ⌘K command palette. Prefers an existing
 *                 palette trigger element; falls back to synthesising the
 *                 Ctrl/Cmd+K keydown the palette already listens for.
 *
 * Delegated listeners, so it works for buttons injected after load. No inline
 * script (CSP-clean); loaded with defer by the shells.
 */
(function () {
  "use strict";

  function openCommandPalette() {
    var trigger = document.querySelector(
      "[data-rmc-cmdk-trigger], #studio-command-palette-btn, " +
        "[data-rmc-command-palette-trigger], [data-rmc-cmdk-open]"
    );
    if (trigger && typeof trigger.click === "function") {
      trigger.click();
      return;
    }
    // Fall back to the global Ctrl/Cmd+K shortcut the palette binds.
    try {
      var ev = new KeyboardEvent("keydown", {
        key: "k",
        code: "KeyK",
        ctrlKey: true,
        metaKey: true,
        bubbles: true,
        cancelable: true,
      });
      document.dispatchEvent(ev);
    } catch (err) {
      /* KeyboardEvent unsupported — no-op rather than throw. */
    }
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) {
      return;
    }
    var pdfBtn = target.closest("[data-rmc-export-pdf]");
    if (pdfBtn) {
      if (!pdfBtn.getAttribute("data-export-url")) {
        event.preventDefault();
        window.print();
      }
      return;
    }
    var quickBtn = target.closest('[data-rmc-quick-action="command-palette"]');
    if (quickBtn) {
      event.preventDefault();
      openCommandPalette();
    }
  });
})();
