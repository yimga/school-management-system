/**
 * RunMyCampus product page — scroll progress and reveal.
 * Product-led storytelling: progress bar + Intersection Observer for .mkt-reveal / .mkt-reveal-stagger.
 * Respects prefers-reduced-motion. Load after marketing-landing-scroll.js (optional).
 */
(function () {
  'use strict';

  var root = document.querySelector('.mkt-product-story[data-scroll-story="true"]');
  if (!root) return;

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var progressWrap = document.getElementById('mkt-product-scroll-progress');
  var progressFill = progressWrap && document.getElementById('mkt-product-scroll-fill');
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
    { root: null, rootMargin: '0px 0px -12% 0px', threshold: 0 }
  );

  revealEls.forEach(function (el) {
    if (reducedMotion) {
      el.classList.add('in-view');
    } else {
      observer.observe(el);
    }
  });
})();
