/* ============================================================
   rmc-app-shell.js — Platform-wide layout shell runtime
   ------------------------------------------------------------
   v3.55.0 / 2026-05-21 — Introduced.

   Pairs with static/css/rmc-app-shell.css. Three behaviors:

     1. ANCHOR-SCROLL RETARGET
        With document scroll locked, `<a href="#section">` clicks
        no longer scroll the document. We intercept hash-clicks
        and hash-changes and scroll the canvas instead.

     2. MODAL PORTAL TELEPORT
        Bootstrap modals rendered inline inside .rmc-app-shell__canvas
        would get clipped by canvas overflow. On `show.bs.modal` we
        teleport the modal to <body> (and restore on hide) so it
        renders over the viewport, not inside the scroll container.

     3. SCROLL HELPER  (window.rmcScrollIntoView)
        Legacy callers that do `el.scrollIntoView()` need to scroll
        the nearest scroll container, not the document. This helper
        finds the canvas (or any other scroll ancestor) and scrolls
        it. Existing call sites are migrated in Phase 4.

   No dependencies. Vanilla JS. Runs at DOMContentLoaded or earlier.
   ============================================================ */
(function () {
  "use strict";

  if (window.rmcAppShellLoaded) {
    return;
  }
  window.rmcAppShellLoaded = true;

  /* ----------------------------------------------------------
     Utility — find the nearest scroll ancestor for an element.
     Walks up the DOM looking for an element with overflow auto/scroll.
     Falls back to the canvas, then to documentElement.
     ---------------------------------------------------------- */
  function findScrollParent(el) {
    if (!el || el === document.documentElement || el === document.body) {
      return document.querySelector(".rmc-app-shell__canvas") || document.documentElement;
    }
    var parent = el.parentElement;
    while (parent) {
      var style = window.getComputedStyle(parent);
      var oy = style.overflowY;
      var ox = style.overflowX;
      var scrolls = (oy === "auto" || oy === "scroll" || ox === "auto" || ox === "scroll");
      if (scrolls && parent.scrollHeight > parent.clientHeight) {
        return parent;
      }
      if (parent.classList && parent.classList.contains("rmc-app-shell__canvas")) {
        return parent;
      }
      parent = parent.parentElement;
    }
    return document.querySelector(".rmc-app-shell__canvas") || document.documentElement;
  }

  /* ----------------------------------------------------------
     Public helper — rmcScrollIntoView(element, options)
     Drop-in for element.scrollIntoView() that targets the right
     scroll container (canvas, not document).
     options accepts the standard ScrollIntoViewOptions shape.
     ---------------------------------------------------------- */
  window.rmcScrollIntoView = function (el, options) {
    if (!el || !(el instanceof Element)) {
      return;
    }
    var container = findScrollParent(el);
    if (!container || container === document.documentElement) {
      // No shell active — fall through to native behavior.
      try {
        el.scrollIntoView(options || { block: "start", behavior: "smooth" });
      } catch (_) {
        /* noop */
      }
      return;
    }
    var prefersReduce = window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var behavior = (options && options.behavior) || (prefersReduce ? "auto" : "smooth");
    var block = (options && options.block) || "start";

    var containerRect = container.getBoundingClientRect();
    var elRect = el.getBoundingClientRect();
    var scrollPadTop = parseFloat(window.getComputedStyle(container).scrollPaddingTop) || 0;

    var top;
    if (block === "center") {
      top = container.scrollTop + (elRect.top - containerRect.top) - (containerRect.height / 2) + (elRect.height / 2);
    } else if (block === "end") {
      top = container.scrollTop + (elRect.bottom - containerRect.top) - containerRect.height;
    } else {
      // start / nearest
      top = container.scrollTop + (elRect.top - containerRect.top) - scrollPadTop;
    }

    try {
      container.scrollTo({ top: top, behavior: behavior });
    } catch (_) {
      container.scrollTop = top;
    }
  };

  /* ----------------------------------------------------------
     Anchor-scroll interception
     Hash links inside the shell scroll the canvas, not the document.
     ---------------------------------------------------------- */
  function handleHashClick(evt) {
    var anchor = evt.target && evt.target.closest && evt.target.closest('a[href^="#"]');
    if (!anchor) {
      return;
    }
    var href = anchor.getAttribute("href");
    if (!href || href === "#" || href.length < 2) {
      return; // dummy anchors — leave alone (or let other handlers preventDefault)
    }
    var id = href.slice(1);
    var target = document.getElementById(id);
    if (!target) {
      return;
    }
    // Only intercept if the target is inside a shell canvas.
    var canvas = target.closest(".rmc-app-shell__canvas");
    if (!canvas) {
      return;
    }
    evt.preventDefault();
    window.rmcScrollIntoView(target, { block: "start" });
    // Update the URL hash without jumping (history without scroll).
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", href);
    }
    // Move focus for accessibility.
    if (target.tabIndex < 0) {
      target.setAttribute("tabindex", "-1");
    }
    target.focus({ preventScroll: true });
  }

  function handleHashChange() {
    var hash = window.location.hash;
    if (!hash || hash.length < 2) {
      return;
    }
    var target = document.getElementById(hash.slice(1));
    if (!target) {
      return;
    }
    var canvas = target.closest(".rmc-app-shell__canvas");
    if (!canvas) {
      return;
    }
    window.rmcScrollIntoView(target, { block: "start" });
  }

  /* ----------------------------------------------------------
     Modal portal teleport (Bootstrap-aware, framework-agnostic)
     When a modal opens, lift it out of the canvas to <body> so
     it isn't clipped by `overflow-x: hidden` on the canvas.
     Restore original position on hide so subsequent re-opens
     find it where the template placed it.
     ---------------------------------------------------------- */
  var modalPlacements = new WeakMap();

  function isInsideCanvas(el) {
    return el && el.closest && !!el.closest(".rmc-app-shell__canvas");
  }

  function teleportModalToBody(modalEl) {
    if (!modalEl || !modalEl.parentNode || modalEl.parentNode === document.body) {
      return;
    }
    if (!isInsideCanvas(modalEl)) {
      return;
    }
    // Record the original parent + next sibling so we can put it back.
    modalPlacements.set(modalEl, {
      parent: modalEl.parentNode,
      next: modalEl.nextSibling
    });
    document.body.appendChild(modalEl);
    modalEl.setAttribute("data-rmc-shell-teleported", "true");
  }

  function restoreModalPlacement(modalEl) {
    if (!modalEl) return;
    var rec = modalPlacements.get(modalEl);
    if (!rec || !rec.parent) {
      return;
    }
    try {
      if (rec.next && rec.next.parentNode === rec.parent) {
        rec.parent.insertBefore(modalEl, rec.next);
      } else {
        rec.parent.appendChild(modalEl);
      }
    } catch (_) {
      /* if the original parent is gone, leave the modal in body */
    }
    modalEl.removeAttribute("data-rmc-shell-teleported");
    modalPlacements.delete(modalEl);
  }

  function attachModalHooks() {
    // Bootstrap 5 fires these events on the modal element.
    document.addEventListener("show.bs.modal", function (evt) {
      teleportModalToBody(evt.target);
    });
    document.addEventListener("hidden.bs.modal", function (evt) {
      restoreModalPlacement(evt.target);
    });
    // Offcanvas (Bootstrap 5) — same clipping risk if placed in canvas.
    document.addEventListener("show.bs.offcanvas", function (evt) {
      teleportModalToBody(evt.target);
    });
    document.addEventListener("hidden.bs.offcanvas", function (evt) {
      restoreModalPlacement(evt.target);
    });
  }

  /* ----------------------------------------------------------
     Header height measurement
     Reads the rendered header height and writes it to a CSS custom
     property so the canvas `scroll-padding-top` lines up. Updated
     on resize + after fonts load (font swap can change line height).
     ---------------------------------------------------------- */
  function syncHeaderHeight() {
    var shell = document.querySelector(".rmc-app-shell");
    if (!shell) return;
    var header = shell.querySelector(".rmc-app-shell__header");
    if (!header) return;
    var h = Math.round(header.getBoundingClientRect().height);
    if (h > 0) {
      shell.style.setProperty("--rmc-app-shell-header-h", h + "px");
    }
  }

  function attachHeaderHeightSync() {
    syncHeaderHeight();
    window.addEventListener("resize", syncHeaderHeight, { passive: true });
    if (document.fonts && document.fonts.ready && typeof document.fonts.ready.then === "function") {
      document.fonts.ready.then(syncHeaderHeight).catch(function () { /* noop */ });
    }
    // ResizeObserver picks up content-driven header growth (e.g. extra row).
    if (typeof ResizeObserver === "function") {
      var header = document.querySelector(".rmc-app-shell__header");
      if (header) {
        var ro = new ResizeObserver(syncHeaderHeight);
        ro.observe(header);
      }
    }
  }

  /* ----------------------------------------------------------
     Sidebar offcanvas toggle wiring (mobile)
     Templates emit a button with [data-rmc-shell-sidebar-toggle]
     and the shell root carries data-rmc-shell-sidebar="offcanvas".
     ---------------------------------------------------------- */
  function attachSidebarToggle() {
    document.addEventListener("click", function (evt) {
      var btn = evt.target && evt.target.closest && evt.target.closest("[data-rmc-shell-sidebar-toggle]");
      if (!btn) return;
      var shell = document.querySelector('.rmc-app-shell[data-rmc-shell-sidebar="offcanvas"]');
      if (!shell) return;
      var open = shell.getAttribute("data-rmc-shell-sidebar-open") === "true";
      shell.setAttribute("data-rmc-shell-sidebar-open", open ? "false" : "true");
      btn.setAttribute("aria-expanded", open ? "false" : "true");
    });

    // Close on ESC + on scrim click.
    document.addEventListener("keydown", function (evt) {
      if (evt.key !== "Escape") return;
      var shell = document.querySelector('.rmc-app-shell[data-rmc-shell-sidebar="offcanvas"][data-rmc-shell-sidebar-open="true"]');
      if (!shell) return;
      shell.setAttribute("data-rmc-shell-sidebar-open", "false");
    });
  }

  /* ----------------------------------------------------------
     Initialization
     ---------------------------------------------------------- */
  /* ----------------------------------------------------------
     RE-HOME EJECTED SHELL CHILDREN  (control-plane resilience)
     The /super/ landing renders a large amount of tenant-data-driven
     markup inside the canvas. If any of it emits a stray or auto-closing
     tag at runtime (e.g. an unescaped data field), the HTML parser closes
     .rmc-app-shell early and the elements the skeleton emits *after* the
     canvas — the copilot rail and the footer — get hoisted out to <body>
     as siblings of the shell. The CSS column-3 pin targets
     `.rmc-app-shell > .rmc-app-shell__copilot`, so once the rail is a body
     child the pin can't reach it and it renders as a stray horizontal band
     instead of docking right. Detect that ejection and move the elements
     back inside the shell so the grid pin applies. Scoped to the
     control-plane shell so the tenant-portal fixed-mount path (where the
     rail is intentionally a <body> child) is never disturbed.
     ---------------------------------------------------------- */
  function rehomeEjectedShellChildren(shell) {
    if (!shell || !document.body.classList.contains("control-plane-shell")) {
      return;
    }
    var selectors = [".rmc-app-shell__copilot", ".rmc-app-shell__footer"];
    var rehomed = [];
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      // Only re-home when the element was hoisted out to <body> by the
      // parser. If it's already inside the shell, leave it untouched.
      if (el && el !== shell && el.parentElement === document.body) {
        shell.appendChild(el);
        rehomed.push(selectors[i]);
      }
    }
    if (rehomed.length) {
      // Surface it: the markup upstream is emitting a stray tag that ejects
      // these. Re-homing fixes the layout, but the source should be found.
      try {
        console.warn(
          "rmc-app-shell: re-homed ejected control-plane shell children " +
            rehomed.join(", ") +
            " (parser closed .rmc-app-shell early — likely a stray/unbalanced tag in canvas markup)"
        );
      } catch (_) {
        /* noop */
      }
    }
  }

  function init() {
    // Only activate behaviors when a shell is actually present.
    var shell = document.querySelector(".rmc-app-shell");
    if (!shell) {
      return;
    }
    rehomeEjectedShellChildren(shell);
    document.addEventListener("click", handleHashClick);
    window.addEventListener("hashchange", handleHashChange);
    attachModalHooks();
    attachHeaderHeightSync();
    attachSidebarToggle();

    // If the page loaded with a hash, scroll to it now (the browser
    // already tried, but with body locked it landed at top).
    if (window.location.hash && window.location.hash.length > 1) {
      // Defer so the layout has settled.
      window.requestAnimationFrame(function () {
        handleHashChange();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
