/**
 * Sheet / modal primitive — drag-to-dismiss, snap detents, scroll-lock, focus
 * + ARIA wiring, and a small public API. Backwards compatible with the v2.6
 * markup contract; richer behavior is opt-in via classes/attributes.
 *
 * Markup contract:
 *   <dialog class="rmc-sheet" id="anything">
 *     <div class="rmc-sheet__handle"></div>
 *     <header class="rmc-sheet__header">
 *       <h3 class="rmc-sheet__title">Title</h3>
 *       <button data-rmc-sheet-close>&times;</button>
 *     </header>
 *     <div class="rmc-sheet__body">…</div>
 *     <footer class="rmc-sheet__footer">…</footer>   (optional)
 *   </dialog>
 *
 * Opt-in classes (CSS in design-tokens.css):
 *   rmc-sheet--sm|md|lg|xl|full   desktop width
 *   rmc-sheet--side[-end]         right-edge drawer on desktop
 *   rmc-sheet--snap               mobile partial-height detent (drag up to expand)
 *
 * Open via element.showModal() OR window.RMCSheet.open(idOrEl). The JS observes
 * the dialog's `open` attribute, so EVERY open path (direct showModal, HTMX
 * swaps, this API) gets scroll-lock + focus + snap, no matter who opened it.
 *
 * Public API — window.RMCSheet:
 *   .open(idOrEl)    showModal() a sheet by id or element
 *   .close(idOrEl)   close it
 *   .toggle(idOrEl)  open if closed, close if open
 *
 * Drag-to-dismiss threshold: down >= 30% of sheet height OR >700px/s velocity.
 * Honors prefers-reduced-motion (CSS drops animations; tap-handle still closes).
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var DRAG_THRESHOLD_PCT = 0.30;
  var DRAG_VELOCITY_PX_PER_S = 700;
  var SNAP_EXPAND_PX = 48; // drag up this far to expand a snap sheet
  var SCROLL_LOCK_CLASS = "rmc-sheet-scroll-lock";

  var openCount = 0;

  function isOnMobileViewport() {
    return window.matchMedia && window.matchMedia("(max-width: 767.98px)").matches;
  }
  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /* ---- scroll-lock (ref-counted across stacked sheets) ---- */
  function lockScroll() {
    openCount += 1;
    if (openCount === 1) document.documentElement.classList.add(SCROLL_LOCK_CLASS);
  }
  function unlockScroll() {
    if (openCount > 0) openCount -= 1;
    if (openCount === 0) document.documentElement.classList.remove(SCROLL_LOCK_CLASS);
  }

  /* ---- a11y: ensure the dialog is labelled by its title ---- */
  var idSeq = 0;
  function wireAria(sheet) {
    if (sheet.getAttribute("aria-label")) return;
    if (sheet.getAttribute("aria-labelledby")) return;
    var title = sheet.querySelector(".rmc-sheet__title");
    if (!title) return;
    if (!title.id) {
      idSeq += 1;
      title.id = "rmc-sheet-title-" + idSeq;
    }
    sheet.setAttribute("aria-labelledby", title.id);
  }

  /* ---- initial focus: explicit autofocus, else first control, else close ---- */
  function focusInitial(sheet) {
    var target =
      sheet.querySelector("[autofocus]") ||
      sheet.querySelector("[data-rmc-sheet-initial-focus]");
    if (!target) {
      var body = sheet.querySelector(".rmc-sheet__body");
      var scope = body || sheet;
      target = scope.querySelector(
        'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
    }
    if (!target) target = sheet.querySelector("[data-rmc-sheet-close]");
    if (target && typeof target.focus === "function") {
      try { target.focus({ preventScroll: true }); } catch (e) { target.focus(); }
    }
  }

  function onOpen(sheet) {
    if (sheet.__rmcSheetOpen) return;
    sheet.__rmcSheetOpen = true;
    /* Remember where focus came from so we can return it on close — but ONLY
       if that element lives outside the sheet. For showModal() the browser has
       already moved focus inside by the time this observer fires (and natively
       restores it on close), so capturing an in-sheet node would wrongly
       override the native restore. Non-modal open paths (HTMX swaps / direct
       `open` attribute) get no native restore, which is the gap this fixes. */
    var __prev = document.activeElement;
    sheet.__rmcReturnFocus = __prev && !sheet.contains(__prev) ? __prev : null;
    lockScroll();
    wireAria(sheet);
    sheet.removeAttribute("data-expanded");
    /* Defer focus a frame so the open animation has laid the sheet out. */
    requestAnimationFrame(function () { focusInitial(sheet); });
  }
  function onClose(sheet) {
    if (!sheet.__rmcSheetOpen) return;
    sheet.__rmcSheetOpen = false;
    unlockScroll();
    sheet.style.removeProperty("transform");
    sheet.removeAttribute("data-dragging");
    /* Return focus to the opener for non-modal open paths, where the native
       <dialog> focus-restore does not run. Guarded so a removed/detached
       opener never throws. */
    var __ret = sheet.__rmcReturnFocus;
    sheet.__rmcReturnFocus = null;
    if (__ret && document.contains(__ret) && typeof __ret.focus === "function") {
      try { __ret.focus({ preventScroll: true }); } catch (e) { try { __ret.focus(); } catch (_e) {} }
    }
  }

  function mount(sheet) {
    if (sheet.__rmcSheetMounted) return;
    sheet.__rmcSheetMounted = true;

    /* Observe the `open` attribute so we catch every open/close path. */
    var observer = new MutationObserver(function () {
      if (sheet.hasAttribute("open")) onOpen(sheet);
      else onClose(sheet);
    });
    observer.observe(sheet, { attributes: true, attributeFilter: ["open"] });
    if (sheet.hasAttribute("open")) onOpen(sheet);

    /* Click-outside-to-close: a click whose target IS the dialog (not its
       content) is a backdrop click. */
    sheet.addEventListener("click", function (e) {
      if (e.target === sheet) sheet.close();
    });

    /* Close buttons. */
    sheet.querySelectorAll("[data-rmc-sheet-close]").forEach(function (btn) {
      btn.addEventListener("click", function () { sheet.close(); });
    });

    /* Drag — only on mobile-shape viewports + touch capable. */
    var handle = sheet.querySelector(".rmc-sheet__handle");
    var header = sheet.querySelector(".rmc-sheet__header");
    var grabTargets = [handle, header].filter(Boolean);
    if (!grabTargets.length) return;
    if (!("ontouchstart" in window) && !navigator.maxTouchPoints) return;

    var isSnap = sheet.classList.contains("rmc-sheet--snap");
    var startY = 0;
    var startTime = 0;
    var currentY = 0; // +down / -up
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
      var delta = touch.clientY - startY;
      var expanded = sheet.getAttribute("data-expanded") === "1";
      /* A snap sheet that isn't expanded yet absorbs UP-drags into expansion
         rather than translating; only DOWN-drags translate (toward dismiss). */
      if (isSnap && !expanded && delta < 0) {
        currentY = 0;
        if (-delta > SNAP_EXPAND_PX) {
          sheet.setAttribute("data-expanded", "1");
          dragging = false;
          sheet.removeAttribute("data-dragging");
        }
        return;
      }
      currentY = Math.max(0, delta);
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
      var expanded = sheet.getAttribute("data-expanded") === "1";
      /* Expanded snap sheet: a modest down-drag collapses back to the detent
         instead of dismissing. */
      if (isSnap && expanded && currentY > 0 && pct <= DRAG_THRESHOLD_PCT &&
          velocity <= DRAG_VELOCITY_PX_PER_S) {
        sheet.removeAttribute("data-expanded");
        sheet.style.removeProperty("transform");
        return;
      }
      if (pct > DRAG_THRESHOLD_PCT || velocity > DRAG_VELOCITY_PX_PER_S) {
        sheet.style.setProperty("transform", "translateY(100%)");
        setTimeout(function () {
          sheet.style.removeProperty("transform");
          sheet.close();
        }, prefersReducedMotion() ? 0 : 220);
      } else {
        sheet.style.removeProperty("transform");
      }
    }

    /* Handle tap toggles expansion on snap sheets (cheap accessibility win). */
    if (isSnap && handle) {
      handle.addEventListener("click", function () {
        if (!isOnMobileViewport()) return;
        if (sheet.getAttribute("data-expanded") === "1") sheet.removeAttribute("data-expanded");
        else sheet.setAttribute("data-expanded", "1");
      });
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

  /* ---- public API ---- */
  function resolve(idOrEl) {
    if (!idOrEl) return null;
    if (typeof idOrEl === "string") return document.getElementById(idOrEl);
    return idOrEl.nodeType === 1 ? idOrEl : null;
  }
  window.RMCSheet = {
    open: function (idOrEl) {
      var el = resolve(idOrEl);
      if (el && typeof el.showModal === "function" && !el.hasAttribute("open")) {
        mount(el);
        el.showModal();
      }
      return el;
    },
    close: function (idOrEl) {
      var el = resolve(idOrEl);
      if (el && typeof el.close === "function" && el.hasAttribute("open")) el.close();
      return el;
    },
    toggle: function (idOrEl) {
      var el = resolve(idOrEl);
      if (!el) return null;
      if (el.hasAttribute("open")) this.close(el);
      else this.open(el);
      return el;
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }
  document.body && document.body.addEventListener("htmx:afterSwap", mountAll);
})();
