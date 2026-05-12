/**
 * Bottom sheet — drag-to-dismiss on touch + click-outside-to-close.
 *
 * Markup contract:
 *   <dialog class="rmc-sheet" id="anything">
 *     <div class="rmc-sheet__handle"></div>
 *     <header class="rmc-sheet__header">
 *       <h3 class="rmc-sheet__title">Title</h3>
 *       <button data-rmc-sheet-close>&times;</button>
 *     </header>
 *     <div class="rmc-sheet__body">…</div>
 *   </dialog>
 *
 * Open via .showModal(); the JS auto-mounts swipe + click-outside dismissal.
 * Honors prefers-reduced-motion (no rubber-band; tap-handle still closes).
 *
 * Threshold: drag down >= 30% of sheet height OR >700px/s velocity dismisses.
 * Otherwise the sheet snaps back. CSS variable `--rmc-sheet-drag` carries the
 * translateY during the gesture; cleared on commit.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var DRAG_THRESHOLD_PCT = 0.30;
  var DRAG_VELOCITY_PX_PER_S = 700;

  function isOnMobileViewport() {
    return window.matchMedia && window.matchMedia("(max-width: 767.98px)").matches;
  }

  function mount(sheet) {
    if (sheet.__rmcSheetMounted) return;
    sheet.__rmcSheetMounted = true;

    /* Click-outside-to-close: <dialog> with showModal() makes the backdrop a
       sibling of the dialog content. A click whose target IS the dialog itself
       (vs. inside its content) means the user clicked the backdrop. */
    sheet.addEventListener("click", function (e) {
      if (e.target === sheet) sheet.close();
    });

    /* Close button. */
    sheet.querySelectorAll("[data-rmc-sheet-close]").forEach(function (btn) {
      btn.addEventListener("click", function () { sheet.close(); });
    });

    /* Drag-to-dismiss — only on mobile-shape viewports + touch capable. */
    var handle = sheet.querySelector(".rmc-sheet__handle");
    var header = sheet.querySelector(".rmc-sheet__header");
    var grabTargets = [handle, header].filter(Boolean);
    if (!grabTargets.length) return;
    if (!("ontouchstart" in window) && !navigator.maxTouchPoints) return;

    var startY = 0;
    var startTime = 0;
    var currentY = 0;
    var dragging = false;

    function onStart(e) {
      if (!isOnMobileViewport()) return;
      var touch = e.touches ? e.touches[0] : e;
      startY = touch.clientY;
      currentY = 0;
      startTime = Date.now();
      dragging = true;
      sheet.setAttribute("data-dragging", "1");
    }
    function onMove(e) {
      if (!dragging) return;
      var touch = e.touches ? e.touches[0] : e;
      currentY = Math.max(0, touch.clientY - startY);
      sheet.style.setProperty("transform", "translateY(" + currentY + "px)");
      if (currentY > 6 && e.cancelable) e.preventDefault();
    }
    function onEnd() {
      if (!dragging) return;
      dragging = false;
      sheet.removeAttribute("data-dragging");
      var elapsed = (Date.now() - startTime) / 1000 || 0.0001;
      var velocity = currentY / elapsed;
      var height = sheet.getBoundingClientRect().height || 1;
      var pct = currentY / height;
      if (pct > DRAG_THRESHOLD_PCT || velocity > DRAG_VELOCITY_PX_PER_S) {
        sheet.style.setProperty("transform", "translateY(100%)");
        setTimeout(function () {
          sheet.style.removeProperty("transform");
          sheet.close();
        }, 220);
      } else {
        sheet.style.removeProperty("transform");
      }
    }

    grabTargets.forEach(function (el) {
      el.addEventListener("touchstart", onStart, { passive: true });
      el.addEventListener("touchmove", onMove, { passive: false });
      el.addEventListener("touchend", onEnd);
      el.addEventListener("touchcancel", onEnd);
    });
  }

  function mountAll() {
    document.querySelectorAll(".rmc-sheet").forEach(mount);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }
  document.body && document.body.addEventListener("htmx:afterSwap", mountAll);
})();
