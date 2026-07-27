/*!
 * rmc-csp-handlers.js — CSP-safe replacements for inline event handlers.
 *
 * A strict `script-src` (no 'unsafe-inline') blocks inline `on*=` attributes and
 * any inline <script> without a nonce. This shared, delegated module lets
 * templates express the common cross-page interactions declaratively via data-*
 * attributes instead of inline handlers:
 *
 *   <button data-rmc-print>                -> window.print()
 *   <button data-rmc-reload>               -> location.reload()
 *   <form   data-rmc-confirm="Message?">   -> confirm() gate before submit
 *   <img    data-rmc-img-fallback>         -> hidden on load error (reveals next sibling)
 *   <link media="print" data-rmc-async-style> -> media flipped to 'all' (async CSS)
 *
 * Loaded from 'self' (external file), so it needs no nonce. Handlers are delegated
 * at the document, so they also cover dynamically-inserted nodes. Page-SPECIFIC
 * logic stays in each page's own nonced <script>; this file owns only the recurring
 * patterns, so the ~112-handler inline-`on*=` burndown can convert to declarative
 * markup instead of re-hosting bespoke JS.
 */
(function () {
  "use strict";

  // --- Async CSS: promote deferred print-media stylesheets to 'all' -----------
  // Replaces the inline `onload="this.media='all'"` on non-render-blocking <link>s.
  // The <link media="print"> still downloads at low priority without blocking the
  // first paint; flipping media to 'all' once parsed applies it — same effect as
  // the old onload, minus the inline handler.
  function promoteAsyncStyles() {
    var links = document.querySelectorAll('link[data-rmc-async-style]');
    for (var i = 0; i < links.length; i++) {
      if (links[i].media !== 'all') {
        links[i].media = 'all';
      }
    }
  }

  // --- Delegated click: print / reload ---------------------------------------
  document.addEventListener('click', function (e) {
    var target = e.target;
    if (!target || !target.closest) {
      return;
    }
    var el = target.closest('[data-rmc-print],[data-rmc-reload]');
    if (!el) {
      return;
    }
    if (el.hasAttribute('data-rmc-print')) {
      window.print();
    } else if (el.hasAttribute('data-rmc-reload')) {
      window.location.reload();
    }
  });

  // --- Delegated submit: confirm() gate before a form posts ------------------
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.matches || !form.matches('form[data-rmc-confirm]')) {
      return;
    }
    var message = form.getAttribute('data-rmc-confirm') || '';
    if (message && !window.confirm(message)) {
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
