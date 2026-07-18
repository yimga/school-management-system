/**
 * Notify opener/parent when a live theme preview surface has rendered.
 * Theme studio listens for {type:'rmc-preview-loaded'} before enabling Confirm.
 */
(function () {
  'use strict';
  function notify() {
    var payload = { type: 'rmc-preview-loaded', url: window.location.href };
    try {
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage(payload, window.location.origin);
      }
    } catch (e) { /* ignore */ }
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(payload, window.location.origin);
      }
    } catch (e2) { /* ignore */ }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', notify);
  } else {
    notify();
  }
})();
