/**
 * Homepage hero video — load + play only when visible; respects reduced motion (CSS hides element).
 */
(function () {
  'use strict';

  var videos = document.querySelectorAll('.mkt-edt-hero__video');
  if (!videos.length) return;

  var reduced =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  videos.forEach(function (video) {
    if (!(video instanceof HTMLVideoElement) || reduced) return;

    function play() {
      if (video.readyState < 1) {
        video.preload = 'metadata';
        video.load();
      }
      var p = video.play();
      if (p && typeof p.catch === 'function') p.catch(function () { /* autoplay policy */ });
    }

    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              play();
            } else {
              video.pause();
            }
          });
        },
        { rootMargin: '64px', threshold: 0.15 }
      );
      observer.observe(video);
    } else {
      play();
    }
  });
})();
