/**
 * Video portal — accessible play/pause for muted inline marketing walkthroughs.
 */
(function () {
  'use strict';

  function boot() {
    document.querySelectorAll('[data-mkt-video-portal]').forEach(function (figure) {
      var video = figure.querySelector('video');
      var btn = figure.querySelector('[data-mkt-video-toggle]');
      var icon = figure.querySelector('[data-mkt-video-icon]');
      if (!video || !btn) return;

      function setState(playing) {
        btn.setAttribute('aria-pressed', playing ? 'true' : 'false');
        btn.setAttribute('aria-label', playing ? 'Pause video' : 'Play video');
        if (icon) icon.textContent = playing ? '❚❚' : '▶';
      }

      btn.addEventListener('click', function () {
        if (video.paused) {
          video.play().then(function () { setState(true); }).catch(function () { setState(false); });
        } else {
          video.pause();
          setState(false);
        }
      });

      video.addEventListener('play', function () { setState(true); });
      video.addEventListener('pause', function () { setState(false); });

      if (video.hasAttribute('autoplay')) {
        video.play().then(function () { setState(true); }).catch(function () { setState(false); });
      } else {
        setState(false);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
