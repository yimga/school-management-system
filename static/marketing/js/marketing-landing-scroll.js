/**
 * RunMyCampus marketing landing — scroll progress + reveal via core; chapter indicator; hero wake.
 * IMPROVEMENTS_RUNBOOK 6.1: uses marketing-scroll-core.js for progress and reveal.
 */
(function () {
  'use strict';

  var root = document.querySelector('.marketing-home[data-scroll-story="true"]');
  if (!root) return;

  if (typeof window.RunMyCampusMarketingScrollCore === 'function') {
    window.RunMyCampusMarketingScrollCore({
      rootSelector: '.marketing-home[data-scroll-story="true"]',
      progressWrapId: 'mkt-scroll-progress',
      progressFillId: 'mkt-scroll-progress-fill',
      revealSelectors: '.mkt-reveal, .mkt-reveal-stagger'
    });
  }

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ----- Chapter indicator: set .active on current section (IMPROVEMENTS_RUNBOOK 2.1) -----
  var chapterIndicator = document.getElementById('mkt-chapter-indicator');
  var chapterDots = chapterIndicator ? chapterIndicator.querySelectorAll('.mkt-chapter-dot') : [];
  var chapterSections = root.querySelectorAll('[data-chapter]');
  function updateChapterIndicator() {
    if (chapterDots.length === 0) return;
    var scrollTop = window.scrollY || document.documentElement.scrollTop;
    var viewportMid = scrollTop + window.innerHeight * 0.35;
    var current = 1;
    chapterSections.forEach(function (section) {
      var ch = parseInt(section.getAttribute('data-chapter'), 10);
      if (!ch) return;
      var rect = section.getBoundingClientRect();
      var top = rect.top + scrollTop;
      if (viewportMid >= top) current = ch;
    });
    chapterDots.forEach(function (dot) {
      var ch = parseInt(dot.getAttribute('data-chapter'), 10);
      dot.classList.toggle('active', ch === current);
    });
  }
  if (chapterDots.length > 0) {
    window.addEventListener('scroll', function () { requestAnimationFrame(updateChapterIndicator); }, { passive: true });
    window.addEventListener('resize', updateChapterIndicator);
    updateChapterIndicator();
  }

  // ----- Hero "wakes up" on scroll: set --hero-reveal 0..1 (IMPROVEMENTS_RUNBOOK 2.2) -----
  var heroVisual = root.querySelector('.mkt-hero-visual-wake');
  if (heroVisual && !reducedMotion) {
    function updateHeroWake() {
      var hero = document.getElementById('hero');
      if (!hero) return;
      var rect = hero.getBoundingClientRect();
      var scrollTop = window.scrollY || document.documentElement.scrollTop;
      var heroBottom = scrollTop + rect.top + rect.height;
      var scrolled = window.scrollY || document.documentElement.scrollTop;
      var reveal = heroBottom <= 0 ? 1 : Math.max(0, Math.min(1, scrolled / (heroBottom - window.innerHeight * 0.5)));
      heroVisual.style.setProperty('--hero-reveal', String(reveal));
    }
    window.addEventListener('scroll', function () { requestAnimationFrame(updateHeroWake); }, { passive: true });
    window.addEventListener('resize', updateHeroWake);
    updateHeroWake();
  }
})();
