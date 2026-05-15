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

  var SELECTOR = ".rmc-reveal:not(.is-revealed)";
  var STAGGER_PARENT_SELECTOR = ".rmc-reveal-stagger";

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

  function setupObserver() {
    if (typeof IntersectionObserver === "undefined") {
      // No IO support — reveal everything immediately. Older Safari/legacy.
      document.querySelectorAll(SELECTOR).forEach(revealNow);
      return null;
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
      {
        rootMargin: "0px 0px -80px 0px",
        threshold: 0.15,
      }
    );
  }

  function observeAll(observer, root) {
    var nodes = (root || document).querySelectorAll(SELECTOR);
    nodes.forEach(function (el) {
      observer.observe(el);
    });
  }

  function init() {
    if (prefersReducedMotion()) {
      // Respect the user. CSS already strips the transition; just flip the class.
      document.querySelectorAll(SELECTOR).forEach(revealNow);
      return;
    }
    assignStaggerIndexes(document);
    var observer = setupObserver();
    if (!observer) return; // already revealed above

    observeAll(observer, document);

    // HTMX support: re-scan after content swaps.
    document.addEventListener("htmx:afterSwap", function (evt) {
      assignStaggerIndexes(evt.target || document);
      observeAll(observer, evt.target || document);
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
