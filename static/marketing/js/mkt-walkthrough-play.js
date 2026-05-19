/**
 * Walkthrough chapter reel — scroll to portal video and play on click.
 */
(function () {
  'use strict';

  function boot() {
    document.querySelectorAll('[data-mkt-walkthrough-play]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var portal = document.getElementById('mkt-walkthrough-portal');
        if (!portal) return;
        portal.scrollIntoView({ behavior: 'smooth', block: 'center' });
        var overlay = portal.querySelector('[data-mkt-video-overlay]');
        if (overlay && !overlay.hidden) {
          overlay.click();
          return;
        }
        var toggle = portal.querySelector('[data-mkt-video-toggle]');
        if (toggle) toggle.click();
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
