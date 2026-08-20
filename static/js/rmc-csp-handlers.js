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
 *   <el     data-rmc-stop-propagation>        -> click does not bubble to a clickable ancestor (was onclick="event.stopPropagation()")
 *   <el     data-rmc-popup [-url|-name|-features]> -> window.open(...) popup       (was onclick="window.open(...)")
 *   <el     data-rmc-click-target="#sel">     -> proxies its click to #sel        (was onclick="document.getElementById('x').click()")
 *   <select data-rmc-navigate-param="k" [data-rmc-navigate-reset="p"]> -> sets ?k=value (resetting p=1) and navigates (was onchange="...searchParams.set(...);window.location=...")
 *   <el     data-rmc-copy-from="#sel">        -> copies #sel text to clipboard
 *   <el     data-rmc-set-and-submit data-rmc-set-field="#f" data-rmc-set-value="v" data-rmc-submit-form="#form"> -> sets #f.value then submits #form (was onclick="document.getElementById('f').value='v';document.getElementById('form').submit()")
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

  // --- window.open popup (replaces onclick="window.open(url, name, features)") -
  function openPopup(el) {
    var url = el.getAttribute('data-rmc-popup-url') || el.getAttribute('href') || '';
    if (!url) {
      return;
    }
    var name = el.getAttribute('data-rmc-popup-name') || '_blank';
    var features = el.getAttribute('data-rmc-popup-features') || '';
    window.open(url, name, features);
  }

  // --- set a field then submit a form (replaces the two-statement inline
  // onclick="document.getElementById('choice').value='x'; form.submit()"). ----
  function applySetAndSubmit(el) {
    var fieldSel = el.getAttribute('data-rmc-set-field');
    if (fieldSel) {
      var field = document.querySelector(fieldSel);
      if (field) {
        field.value = el.getAttribute('data-rmc-set-value') || '';
      }
    }
    var formSel = el.getAttribute('data-rmc-submit-form');
    var form = formSel ? document.querySelector(formSel) : null;
    if (form && typeof form.submit === 'function') {
      form.submit();
    }
  }

  // --- Delegated click: print / reload / select-field / popup / proxy / submit -
  document.addEventListener('click', function (e) {
    var target = e.target;
    if (!target || !target.closest) {
      return;
    }
    var el = target.closest(
      '[data-rmc-print],[data-rmc-reload],[data-rmc-select-on-click],' +
      '[data-rmc-popup],[data-rmc-click-target],[data-rmc-set-and-submit],' +
      '[data-rmc-open-shortcuts],[data-rmc-copy-from]'
    );
    if (!el) {
      return;
    }
    if (el.hasAttribute('data-rmc-print')) {
      window.print();
    } else if (el.hasAttribute('data-rmc-reload')) {
      window.location.reload();
    } else if (el.hasAttribute('data-rmc-select-on-click') && typeof el.select === 'function') {
      el.select();
    } else if (el.hasAttribute('data-rmc-popup')) {
      e.preventDefault();
      openPopup(el);
    } else if (el.hasAttribute('data-rmc-click-target')) {
      e.preventDefault();
      var proxySel = el.getAttribute('data-rmc-click-target');
      var proxied = proxySel ? document.querySelector(proxySel) : null;
      if (proxied && typeof proxied.click === 'function') {
        proxied.click();
      }
    } else if (el.hasAttribute('data-rmc-set-and-submit')) {
      e.preventDefault();
      applySetAndSubmit(el);
    } else if (el.hasAttribute('data-rmc-open-shortcuts')) {
      // Opens the keyboard-shortcut cheat sheet (also reachable via `?`).
      e.preventDefault();
      if (window.RMCShortcuts && typeof window.RMCShortcuts.open === 'function') {
        window.RMCShortcuts.open();
      }
    } else if (el.hasAttribute('data-rmc-copy-from')) {
      e.preventDefault();
      var fromSel = el.getAttribute('data-rmc-copy-from');
      var fromEl = fromSel ? document.querySelector(fromSel) : null;
      var copyText = fromEl ? (fromEl.innerText || fromEl.textContent || '') : '';
      if (copyText && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(copyText).then(function () {
          el.classList.add('is-copied');
          window.setTimeout(function () { el.classList.remove('is-copied'); }, 1600);
        }, function () {});
      }
    }
  });

  // --- Delegated change: submit the control's owner form ---------------------
  // Replaces onchange="this.form.submit()" on filter <select>s. Uses `.form`
  // (the element's owner form, honoring a `form=` attribute) with a `closest`
  // fallback. Calls form.submit() directly — matching the old inline handler,
  // which likewise bypassed the submit event / native validation.
  document.addEventListener('change', function (e) {
    var el = e.target;
    if (!el || !el.hasAttribute) {
      return;
    }
    if (el.hasAttribute('data-rmc-submit-on-change')) {
      var form = el.form || (el.closest ? el.closest('form') : null);
      if (form) {
        form.submit();
      }
      return;
    }
    if (el.hasAttribute('data-rmc-navigate-param')) {
      navigateWithParam(el);
    }
  });

  // --- Navigate by rewriting a query param (replaces the page-size select's
  // onchange="var u=new URL(...);u.searchParams.set('page_size',this.value);
  // window.location=u..."). Optional data-rmc-navigate-reset lists params to
  // reset to '1' (e.g. jump back to page 1 when the page size changes). --------
  function navigateWithParam(el) {
    var param = el.getAttribute('data-rmc-navigate-param');
    if (!param) {
      return;
    }
    var url = new URL(window.location.href);
    url.searchParams.set(param, el.value);
    var resetList = (el.getAttribute('data-rmc-navigate-reset') || '').split(/[\s,]+/);
    for (var i = 0; i < resetList.length; i++) {
      if (resetList[i]) {
        url.searchParams.set(resetList[i], '1');
      }
    }
    window.location.assign(url.toString());
  }

  // --- Delegated input: derive a sibling field's NAME from this field's value -
  // Replaces oninput="document.getElementById('x').name='subject_'+this.value.toUpperCase()"
  // on the "add subject (CODE:value)" inputs — typing a CA code sets the paired
  // value input's submit name (subject_<CODE>) so the new column posts correctly.
  document.addEventListener('input', function (e) {
    var el = e.target;
    if (!el || !el.getAttribute) {
      return;
    }
    var targetSel = el.getAttribute('data-rmc-derive-name-target');
    if (!targetSel) {
      return;
    }
    var target = document.querySelector(targetSel);
    if (!target) {
      return;
    }
    var prefix = el.getAttribute('data-rmc-derive-name-prefix') || '';
    target.name = prefix + (el.value || '').toUpperCase();
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

  // --- Stop-propagation: a TARGET-phase click guard --------------------------
  // Replaces onclick="event.stopPropagation()" on a control nested inside a
  // clickable row/card, keeping a button/link click from also firing the
  // ancestor's handler. This one CANNOT be document-delegated: a document
  // listener runs at the END of bubbling, after the ancestor already handled the
  // click. Binding directly on the element (target phase) matches the inline
  // handler's timing — and stopPropagation on the element does not suppress
  // OTHER listeners on that same element (e.g. data-rmc-approve-request), only
  // the bubble to ancestors.
  function bindStopPropagation() {
    var nodes = document.querySelectorAll('[data-rmc-stop-propagation]');
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].addEventListener('click', function (ev) {
        ev.stopPropagation();
      });
    }
  }

  function onReady() {
    promoteAsyncStyles();
    bindStopPropagation();
  }

  // The script is deferred, so the DOM is normally parsed by the time it runs;
  // guard anyway so an early/non-deferred load still initialises on DOMContentLoaded.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})();
