/**
 * RunMyCampus marketing landing — scroll-storytelling.
 * Intersection Observer for .mkt-reveal / .mkt-reveal-stagger; scroll progress bar.
 * Progressive enhancement; respects prefers-reduced-motion.
 */
(function () {
  'use strict';

  var root = document.querySelector('.marketing-home[data-scroll-story="true"]');
  if (!root) return;

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ----- Scroll progress bar -----
  var progressWrap = document.getElementById('mkt-scroll-progress');
  var progressFill = progressWrap && document.getElementById('mkt-scroll-progress-fill');
  function updateProgress() {
    if (!progressFill) return;
    var scrollTop = window.scrollY || document.documentElement.scrollTop;
    var docHeight = document.documentElement.scrollHeight - window.innerHeight;
    var pct = docHeight <= 0 ? 100 : Math.min(100, (scrollTop / docHeight) * 100);
    progressFill.style.width = pct + '%';
  }
  if (progressWrap && progressFill && !reducedMotion) {
    window.addEventListener('scroll', function () { requestAnimationFrame(updateProgress); }, { passive: true });
    window.addEventListener('resize', updateProgress);
    updateProgress();
  }

  // ----- Reveal on scroll (Intersection Observer) -----
  var revealEls = root.querySelectorAll('.mkt-reveal, .mkt-reveal-stagger');
  if (revealEls.length === 0) return;

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in-view');
          observer.unobserve(entry.target);
        }
      });
    },
    {
      root: null,
      rootMargin: '0px 0px -12% 0px',
      threshold: 0
    }
  );

  revealEls.forEach(function (el) {
    if (reducedMotion) {
      el.classList.add('in-view');
    } else {
      observer.observe(el);
    }
  });
})();
