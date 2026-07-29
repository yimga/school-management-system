/**
 * rmc-reveal.js — Apple HIG scroll-reveal grammar.
 *
 * Adds .is-revealed to any element carrying .rmc-reveal when it scrolls into
 * the viewport. Paired with the CSS in design-tokens.css (v2.26 layer), which
 * defines initial opacity/transform + the transition. JS only flips the
 * is-revealed class; CSS owns the actual motion.
 *
 * Design choices:
 *   - rootMargin: -80px on top so reveal fires *after* the element is well
 *     into the viewport, not the instant 1px peeks. Feels intentional, not
 *     twitchy.
 *   - threshold: 0.15 so partial entries (long elements) reveal at the
 *     same moment a reader's eye lands on them.
 *   - one-shot: we unobserve after revealing. No flicker on scrollback.
 *   - prefers-reduced-motion: immediately mark every element revealed, no
 *     observer needed. CSS already removes the transition.
 *   - Stagger groups: a parent with .rmc-reveal-stagger gets its direct
 *     .rmc-reveal children assigned --reveal-index automatically based on
 *     DOM order. Lets sibling sequences cascade.
 *   - HTMX-friendly: re-scans on htmx:afterSwap so dynamically inserted
 *     content also reveals.
 */
(function () {
  "use strict";

  if (typeof document === "undefined") return;

  // Defense-in-depth: arm the reveal-hides-content CSS only when this script
  // actually parsed. If the file fails to load (CSP block, stale-cache 404,
  // network error), the html flag is never set, design-tokens.css skips the
  // opacity:0 rule, and content stays visible instead of becoming permanently
  // hidden — the failure mode that produced the blank-app-catalog bug.
  try { document.documentElement.setAttribute("data-rmc-reveal-armed", "1"); } catch (_e) {}

  var SELECTOR = ".rmc-reveal:not(.is-revealed)";
  var STAGGER_PARENT_SELECTOR = ".rmc-reveal-stagger";
  var SCROLL_ROOT_SELECTORS =
    "#cp-main-content, #main-content, .rmc-app-shell__canvas, [data-rmc-shell-canvas], main[role='main'], main";

  function prefersReducedMotion() {
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (_e) {
      return false;
    }
  }

  function assignStaggerIndexes(root) {
    var parents = (root || document).querySelectorAll(STAGGER_PARENT_SELECTOR);
    parents.forEach(function (parent) {
      var children = parent.children;
      var i = 0;
      for (var n = 0; n < children.length; n++) {
        var child = children[n];
        if (child.classList && child.classList.contains("rmc-reveal")) {
          // Only set if not already authored — respect explicit overrides.
          if (!child.style.getPropertyValue("--reveal-index")) {
            child.style.setProperty("--reveal-index", String(i));
          }
          i++;
        }
      }
    });
  }

  function revealNow(el) {
    el.classList.add("is-revealed");
  }

  /** Shell scroll container (#cp-main-content / #main-content) when overflow-y scrolls. */
  function resolveScrollRoot() {
    var nodes = document.querySelectorAll(SCROLL_ROOT_SELECTORS);
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var oy = window.getComputedStyle(el).overflowY;
      if (oy === "auto" || oy === "scroll" || oy === "overlay") {
        return el;
      }
    }
    return null;
  }

  /** Reveal nodes already visible inside the scroll root (IO viewport-root miss). */
  function revealVisibleInRoot(scrollRoot) {
    var bounds;
    if (scrollRoot) {
      bounds = scrollRoot.getBoundingClientRect();
    } else {
      bounds = {
        top: 0,
        left: 0,
        bottom: window.innerHeight,
        right: window.innerWidth,
      };
    }
    document.querySelectorAll(SELECTOR).forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (
        r.bottom > bounds.top &&
        r.top < bounds.bottom &&
        r.right > bounds.left &&
        r.left < bounds.right
      ) {
        revealNow(el);
      }
    });
  }

  function countRevealState() {
    var nodes = document.querySelectorAll(".rmc-reveal");
    var hidden = 0;
    var unrevealed = 0;
    nodes.forEach(function (el) {
      if (!el.classList.contains("is-revealed")) unrevealed += 1;
      if (parseFloat(window.getComputedStyle(el).opacity) < 0.05) hidden += 1;
    });
    return { total: nodes.length, unrevealed: unrevealed, hiddenOpacity: hidden };
  }

  function setupObserver(scrollRoot) {
    if (typeof IntersectionObserver === "undefined") {
      // No IO support — reveal everything immediately. Older Safari/legacy.
      document.querySelectorAll(SELECTOR).forEach(revealNow);
      return null;
    }
    var opts = {
      // Viewport-root: inset top so reveal fires after the element is in-frame.
      // Scroll-root (#cp-main-content / #main-content): zero margin — negative
      // margins shrink the root rect and strand below-fold cards at opacity:0
      // (abrupt page end on manager/configuration + /super/*).
      rootMargin: scrollRoot ? "0px" : "0px 0px -80px 0px",
      threshold: scrollRoot ? [0] : [0, 0.15],
    };
    if (scrollRoot) {
      opts.root = scrollRoot;
    }
    return new IntersectionObserver(
      function (entries, observer) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            revealNow(entry.target);
            observer.unobserve(entry.target);
          }
        });
      },
      opts
    );
  }

  function observeAll(observer, root) {
    var nodes = (root || document).querySelectorAll(SELECTOR);
    nodes.forEach(function (el) {
      observer.observe(el);
    });
  }

  function revealAllStranded() {
    document.querySelectorAll(".rmc-reveal:not(.is-revealed)").forEach(revealNow);
  }

  function scheduleGlobalRevealFailsafe() {
    window.setTimeout(function () {
      if (countRevealState().hiddenOpacity > 0) {
        revealAllStranded();
      }
    }, 1200);
  }

  function revealOperationalWorkspaces() {
    var roots = document.querySelectorAll(
      "#workflow-main, .tp-workflow-portal, [data-rmc-command-workspace='workflow-center'], [data-rmc-teacher-workflow-redesign='1'], [data-rmc-operational-workbench='1']"
    );
    roots.forEach(function (root) {
      root.querySelectorAll(".rmc-reveal:not(.is-revealed)").forEach(revealNow);
    });
  }

  function init() {
    revealOperationalWorkspaces();
    if (prefersReducedMotion()) {
      // Respect the user. CSS already strips the transition; just flip the class.
      document.querySelectorAll(SELECTOR).forEach(revealNow);
      return;
    }
    // Django admin: never leave chrome/content at opacity:0 waiting for IO.
    // Tenant used to miss the scroll root (#cp-main-content vs canvas), which
    // matched "blank until click then content appears".
    var body = document.body;
    if (
      body &&
      (body.classList.contains("admin-premium-shell") ||
        body.classList.contains("admin-manager-shell") ||
        body.getAttribute("data-rmc-shell-root") === "django-admin")
    ) {
      document.querySelectorAll(SELECTOR).forEach(revealNow);
      return;
    }
    assignStaggerIndexes(document);
    var scrollRoot = resolveScrollRoot();
    var observer = setupObserver(scrollRoot);
    if (!observer) {
      scheduleGlobalRevealFailsafe();
      return; // already revealed above
    }

    observeAll(observer, document);
    revealVisibleInRoot(scrollRoot);
    scheduleGlobalRevealFailsafe();

    if (scrollRoot) {
      function revealAllInScrollRoot() {
        scrollRoot
          .querySelectorAll(".rmc-reveal:not(.is-revealed)")
          .forEach(revealNow);
      }

      var scrollTimer = null;
      function onScrollRootScroll() {
        if (scrollTimer) return;
        scrollTimer = window.setTimeout(function () {
          scrollTimer = null;
          revealVisibleInRoot(scrollRoot);
          var nearEnd =
            scrollRoot.scrollTop + scrollRoot.clientHeight >=
            scrollRoot.scrollHeight - 48;
          if (nearEnd) {
            revealAllInScrollRoot();
          }
        }, 48);
      }

      function onFirstUserScrollIntent() {
        revealAllInScrollRoot();
      }

      scrollRoot.addEventListener("scroll", onScrollRootScroll, { passive: true });
      scrollRoot.addEventListener("wheel", onFirstUserScrollIntent, {
        passive: true,
        once: true,
      });
      scrollRoot.addEventListener(
        "touchstart",
        onFirstUserScrollIntent,
        { passive: true, once: true }
      );

      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () {
          revealVisibleInRoot(scrollRoot);
          onScrollRootScroll();
        });
      });

      // Never strand below-fold cards when the shell column scrolls (manager
      // / portal / admin). IO + scroll catch-up can miss headless/programmatic
      // scroll; this fallback matches user-visible content within one frame budget.
      window.setTimeout(function () {
        if (countRevealState().unrevealed > 0) {
          revealAllInScrollRoot();
        }
      }, 400);
    }

    // HTMX support: re-scan after content swaps.
    document.addEventListener("htmx:afterSwap", function (evt) {
      assignStaggerIndexes(evt.target || document);
      observeAll(observer, evt.target || document);
      revealVisibleInRoot(scrollRoot);
    });

    // Live-region support: any node mutation under <main> that adds
    // .rmc-reveal children gets picked up too. Cheap MutationObserver.
    var main = document.querySelector("main") || document.body;
    if (main && typeof MutationObserver !== "undefined") {
      var mo = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          m.addedNodes &&
            m.addedNodes.forEach(function (node) {
              if (node.nodeType !== 1) return;
              if (
                node.classList &&
                node.classList.contains("rmc-reveal") &&
                !node.classList.contains("is-revealed")
              ) {
                observer.observe(node);
              }
              if (node.querySelectorAll) {
                assignStaggerIndexes(node);
                observeAll(observer, node);
              }
            });
        });
      });
      mo.observe(main, { childList: true, subtree: true });
    }
  }

  function safeInit() {
    try {
      init();
    } catch (_e) {
      revealAllStranded();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", safeInit);
  } else {
    safeInit();
  }
})();
