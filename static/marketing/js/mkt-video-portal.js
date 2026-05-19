/**
 * Video portal — play/pause, in-view autoplay (muted), click-to-play overlay.
 */
(function () {
  'use strict';

  var reduced =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function ensureLoaded(video) {
    if (video.readyState >= 1) return Promise.resolve();
    video.preload = 'auto';
    return new Promise(function (resolve) {
      function done() {
        video.removeEventListener('loadeddata', done);
        video.removeEventListener('error', done);
        resolve();
      }
      video.addEventListener('loadeddata', done);
      video.addEventListener('error', done);
      video.load();
    });
  }

  function playVideo(video) {
    return ensureLoaded(video).then(function () {
      return video.play();
    });
  }

  function boot() {
    document.querySelectorAll('[data-mkt-video-portal]').forEach(function (figure) {
      var video = figure.querySelector('video');
      var btn = figure.querySelector('[data-mkt-video-toggle]');
      var overlay = figure.querySelector('[data-mkt-video-overlay]');
      var icon = figure.querySelector('[data-mkt-video-icon]');
      if (!video) return;

      var autoplayInView = figure.getAttribute('data-autoplay-in-view') !== '0';

      function setState(playing) {
        figure.classList.toggle('is-playing', playing);
        figure.classList.toggle('is-paused', !playing);
        if (btn) {
          btn.setAttribute('aria-pressed', playing ? 'true' : 'false');
          btn.setAttribute('aria-label', playing ? 'Pause video' : 'Play video');
        }
        if (icon) icon.textContent = playing ? '❚❚' : '▶';
        if (overlay) overlay.hidden = playing;
      }

      function togglePlay() {
        if (video.paused) {
          playVideo(video)
            .then(function () { setState(true); })
            .catch(function () {
              setState(false);
              figure.classList.add('is-error');
            });
        } else {
          video.pause();
          setState(false);
        }
      }

      if (btn) btn.addEventListener('click', function (e) { e.stopPropagation(); togglePlay(); });
      if (overlay) overlay.addEventListener('click', togglePlay);
      figure.addEventListener('click', function (e) {
        if (e.target === video) togglePlay();
      });

      video.addEventListener('play', function () { setState(true); figure.classList.remove('is-error'); });
      video.addEventListener('pause', function () { setState(false); });

      setState(false);

      if (reduced || !autoplayInView) return;

      if ('IntersectionObserver' in window) {
        var observer = new IntersectionObserver(
          function (entries) {
            entries.forEach(function (entry) {
              if (entry.isIntersecting && entry.intersectionRatio >= 0.35) {
                playVideo(video).then(function () { setState(true); }).catch(function () { setState(false); });
              } else if (!video.paused) {
                video.pause();
              }
            });
          },
          { threshold: [0, 0.35, 0.6], rootMargin: '48px' }
        );
        observer.observe(figure);
      } else {
        playVideo(video).then(function () { setState(true); }).catch(function () { setState(false); });
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
