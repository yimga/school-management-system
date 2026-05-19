/**
 * Homepage hero video — in-view autoplay, click overlay, metadata preload.
 */
(function () {
  'use strict';

  var reduced =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function boot() {
    document.querySelectorAll('[data-mkt-hero-media]').forEach(function (wrap) {
      var video = wrap.querySelector('.mkt-edt-hero__video');
      if (!(video instanceof HTMLVideoElement) || reduced) return;

      var overlay = wrap.querySelector('[data-mkt-hero-video-overlay]');
      video.preload = 'metadata';

      function setPlaying(playing) {
        wrap.classList.toggle('is-playing', playing);
        if (overlay) overlay.hidden = playing;
      }

      function play() {
        if (video.readyState < 1) video.load();
        return video.play().then(function () { setPlaying(true); }).catch(function () { setPlaying(false); });
      }

      function toggle() {
        if (video.paused) play();
        else { video.pause(); setPlaying(false); }
      }

      if (overlay) overlay.addEventListener('click', toggle);
      wrap.addEventListener('click', function (e) {
        if (e.target === video || e.target === wrap) toggle();
      });
      video.addEventListener('play', function () { setPlaying(true); });
      video.addEventListener('pause', function () { setPlaying(false); });
      setPlaying(false);

      if ('IntersectionObserver' in window) {
        var observer = new IntersectionObserver(
          function (entries) {
            entries.forEach(function (entry) {
              if (entry.isIntersecting && entry.intersectionRatio >= 0.2) play();
              else if (!video.paused) video.pause();
            });
          },
          { rootMargin: '64px', threshold: [0, 0.2, 0.5] }
        );
        observer.observe(video);
      } else {
        play();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
