/*!
 * rmc-csp-handlers.js — CSP-safe replacements for inline event handlers.
 *
 * A strict `script-src` (no 'unsafe-inline') blocks inline `on*=` attributes and
 * any inline <script> without a nonce. This shared, delegated module lets
 * templates express the common cross-page interactions declaratively via data-*
 * attributes instead of inline handlers:
 *
 *   <button data-rmc-print>                   -> window.print()
 *   <button data-rmc-reload>                  -> location.reload()
 *   <img    data-rmc-img-fallback>            -> hidden on load error (reveals next sibling)
 *   <link   data-rmc-async-style>             -> deferred CSS applied (media 'print'->'all', OR rel 'preload'->'stylesheet')
 *   <select data-rmc-submit-on-change>        -> owner form submitted on change  (was onchange="this.form.submit()")
 *   <input  data-rmc-select-on-click>         -> field text selected on click    (was onclick="this.select()")
 *   <input  data-rmc-select-on-focus>         -> field text selected on focus     (was onfocus="this.select()")
 *   <form   data-rmc-noop-submit>             -> submit suppressed (JS-driven form) (was onsubmit="return false")
 *
 * NOTE: `data-rmc-confirm` (confirm-before-submit) is intentionally NOT handled
 * here — the platform's rich modal handler `rmc-modal-intelligence.js` owns that
 * declarative marker (a styled sheet, not native confirm()). Adding a second
 * handler here would double-prompt.
 *
 * Loaded from 'self' (external file), so it needs no nonce. Handlers are delegated
 * at the document, so they also cover dynamically-inserted nodes. Page-SPECIFIC
 * logic stays in each page's own nonced <script>; this file owns only the recurring
 * patterns, so the inline-`on*=` burndown can convert to declarative markup
 * instead of re-hosting bespoke JS.
 */
(function () {
  "use strict";

  // --- Async CSS: apply a deferred (non-render-blocking) stylesheet ------------
  // Replaces two inline patterns that both defer CSS past first paint:
  //   1. `onload="this.media='all'"`         on a <link media="print">   (media flip)
  //   2. `onload="this.onload=null;this.rel='stylesheet'"` on a <link rel="preload" as="style"> (rel flip)
  // Both download at low priority without blocking the first paint; promoting them
  // once the DOM is parsed applies the CSS — same effect as the old onload handler,
  // minus the inline attribute. A <noscript> fallback still covers the no-JS path.
  function promoteAsyncStyles() {
    var links = document.querySelectorAll('link[data-rmc-async-style]');
    for (var i = 0; i < links.length; i++) {
      var link = links[i];
      if ((link.getAttribute('rel') || '').toLowerCase() === 'preload') {
        link.rel = 'stylesheet';
      } else if (link.media !== 'all') {
        link.media = 'all';
      }
    }
  }

  // --- Delegated click: print / reload / select-field ------------------------
  document.addEventListener('click', function (e) {
    var target = e.target;
    if (!target || !target.closest) {
      return;
    }
    var el = target.closest('[data-rmc-print],[data-rmc-reload],[data-rmc-select-on-click]');
    if (!el) {
      return;
    }
    if (el.hasAttribute('data-rmc-print')) {
      window.print();
    } else if (el.hasAttribute('data-rmc-reload')) {
      window.location.reload();
    } else if (el.hasAttribute('data-rmc-select-on-click') && typeof el.select === 'function') {
      el.select();
    }
  });

  // --- Delegated change: submit the control's owner form ---------------------
  // Replaces onchange="this.form.submit()" on filter <select>s. Uses `.form`
  // (the element's owner form, honoring a `form=` attribute) with a `closest`
  // fallback. Calls form.submit() directly — matching the old inline handler,
  // which likewise bypassed the submit event / native validation.
  document.addEventListener('change', function (e) {
    var el = e.target;
    if (!el || !el.hasAttribute || !el.hasAttribute('data-rmc-submit-on-change')) {
      return;
    }
    var form = el.form || (el.closest ? el.closest('form') : null);
    if (form) {
      form.submit();
    }
  });

  // --- Delegated focus: select the field's text ------------------------------
  // Replaces onfocus="this.select()" on read-only copy-me inputs. `focus` does
  // not bubble, so the bubbling `focusin` is used for delegation.
  document.addEventListener('focusin', function (e) {
    var el = e.target;
    if (
      el &&
      el.hasAttribute &&
      el.hasAttribute('data-rmc-select-on-focus') &&
      typeof el.select === 'function'
    ) {
      el.select();
    }
  });

  // --- Delegated submit: suppress submit on JS-driven forms ------------------
  // Replaces onsubmit="return false" on forms whose submission is handled in JS
  // (AI assistant docks, etc.). `submit` bubbles, so document delegation covers
  // it; preventDefault runs before the default navigation.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (form && form.hasAttribute && form.hasAttribute('data-rmc-noop-submit')) {
      e.preventDefault();
    }
  });

  // --- Delegated image error: hide the broken image, reveal its fallback -----
  // The 'error' event does not bubble, so it is captured at the document root.
  document.addEventListener('error', function (e) {
    var img = e.target;
    if (
      !img ||
      img.tagName !== 'IMG' ||
      !img.hasAttribute ||
      !img.hasAttribute('data-rmc-img-fallback')
    ) {
      return;
    }
    img.style.display = 'none';
    var next = img.nextElementSibling;
    if (next) {
      next.style.display = 'inline-flex';
    }
  }, true);

  // The script is deferred, so the DOM is normally parsed by the time it runs;
  // guard anyway so an early/non-deferred load still promotes on DOMContentLoaded.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', promoteAsyncStyles);
  } else {
    promoteAsyncStyles();
  }
})();
