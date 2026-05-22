// rmc-collapsable.js — v3.58.x (2026-05-22) Wave 10 Agent T
//
// Reusable collapsable-section primitive. The DOM contract is a native
// <details class="rmc-collapsable"> with these data attributes:
//
//   data-rmc-collapsable-key       — required. localStorage key suffix.
//                                    Final key is "rmc-collapsable-<key>".
//   data-rmc-collapsable-default   — "open" (default) or "collapsed". Used
//                                    when localStorage has no prior state
//                                    AND the [open] attribute is absent.
//   data-rmc-collapsable-persist   — "true" (default) or "false". When
//                                    "false", state is NOT persisted across
//                                    visits — used for transient banners.
//
// Persistence behavior:
//   - Stored value is the literal string "open" or "collapsed".
//   - Stored values WIN over the [open] attribute from server-side render
//     (operator preference is the source of truth once expressed).
//   - localStorage failure (private mode, full quota) degrades to in-memory
//     only — the toggle still works for the current page view.
//
// CSP-friendly: external script, no inline handlers.
// Idempotent: re-running on each <details> via dataset.rmcCollapsableInited.

(function () {
  'use strict';

  var STORAGE_PREFIX = 'rmc-collapsable-';

  // Module-load gate: do nothing on pages that have no collapsable sections
  // so we don't pay for a query/init on every page in the platform.
  if (!document.querySelectorAll('.rmc-collapsable').length) return;

  function safeGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function safeSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      // private mode / quota exceeded — ignore; in-memory state still works
    }
  }

  function persistAllowed(el) {
    return el.dataset.rmcCollapsablePersist !== 'false';
  }

  function defaultState(el) {
    return el.dataset.rmcCollapsableDefault === 'collapsed' ? 'collapsed' : 'open';
  }

  function applyState(el, state) {
    // <details> open property is the canonical toggle.
    el.open = (state === 'open');
    el.setAttribute(
      'data-rmc-collapsable-state',
      state === 'open' ? 'open' : 'collapsed'
    );
  }

  function initOne(el) {
    if (el.dataset.rmcCollapsableInited === '1') return;
    el.dataset.rmcCollapsableInited = '1';

    var key = el.dataset.rmcCollapsableKey;
    if (!key) {
      // No key => no persistence; still wire the state attribute mirror
      // so CSS hooks like [data-rmc-collapsable-state="collapsed"] work.
      applyState(el, el.open ? 'open' : 'collapsed');
      el.addEventListener('toggle', function () {
        applyState(el, el.open ? 'open' : 'collapsed');
      });
      return;
    }

    var storageKey = STORAGE_PREFIX + key;
    var persist = persistAllowed(el);

    // Resolve initial state:
    //   1. localStorage (if persistence enabled)
    //   2. server-rendered [open] attribute (when explicitly authored)
    //   3. data-rmc-collapsable-default
    var initial = null;
    if (persist) {
      var stored = safeGet(storageKey);
      if (stored === 'open' || stored === 'collapsed') {
        initial = stored;
      }
    }
    if (initial === null) {
      // Honor the server-rendered [open] attribute when no stored preference
      // exists. Some pages author [open] explicitly because the section is
      // landing-critical.
      if (el.hasAttribute('open')) {
        initial = 'open';
      } else {
        initial = defaultState(el);
      }
    }
    applyState(el, initial);

    // Persist on user toggle. <details> fires "toggle" after el.open changes.
    el.addEventListener('toggle', function () {
      var state = el.open ? 'open' : 'collapsed';
      applyState(el, state);
      if (persist) {
        safeSet(storageKey, state);
      }
    });
  }

  function initAll() {
    var nodes = document.querySelectorAll('.rmc-collapsable');
    Array.prototype.forEach.call(nodes, initOne);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
