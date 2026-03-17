/**
 * RunMyCampus marketing scroll core — shared progress bar + reveal on scroll.
 * Used by marketing-landing-scroll.js and marketing-product-scroll.js.
 * Options: { rootSelector, progressWrapId, progressFillId, revealSelectors }.
 * Respects prefers-reduced-motion.
 */
(function (global) {
  'use strict';

  function runScrollCore(options) {
    var rootSelector = options.rootSelector;
    var progressWrapId = options.progressWrapId;
    var progressFillId = options.progressFillId;
    var revealSelectors = options.revealSelectors || '.mkt-reveal, .mkt-reveal-stagger';

    var root = document.querySelector(rootSelector);
    if (!root) return;

    var reducedMotion = global.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (progressWrapId && progressFillId) {
      var progressWrap = document.getElementById(progressWrapId);
      var progressFill = document.getElementById(progressFillId);
      function updateProgress() {
        if (!progressFill) return;
        var scrollTop = global.scrollY || document.documentElement.scrollTop;
        var docHeight = document.documentElement.scrollHeight - global.innerHeight;
        var pct = docHeight <= 0 ? 100 : Math.min(100, (scrollTop / docHeight) * 100);
        progressFill.style.width = pct + '%';
      }
      if (progressWrap && progressFill && !reducedMotion) {
        global.addEventListener('scroll', function () { global.requestAnimationFrame(updateProgress); }, { passive: true });
        global.addEventListener('resize', updateProgress);
        updateProgress();
      }
    }

    var revealEls = root.querySelectorAll(revealSelectors);
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
  }

  global.RunMyCampusMarketingScrollCore = runScrollCore;
})(typeof window !== 'undefined' ? window : this);
