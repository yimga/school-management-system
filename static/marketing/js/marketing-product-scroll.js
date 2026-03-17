/**
 * RunMyCampus product page — scroll progress + reveal via core; pinned product frame per chapter (GAP.1).
 * IMPROVEMENTS_RUNBOOK 6.1: uses marketing-scroll-core.js for progress and reveal.
 */
(function () {
  'use strict';

  var root = document.querySelector('.mkt-product-story[data-scroll-story="true"]');
  if (!root) return;

  if (typeof window.RunMyCampusMarketingScrollCore === 'function') {
    window.RunMyCampusMarketingScrollCore({
      rootSelector: '.mkt-product-story[data-scroll-story="true"]',
      progressWrapId: 'mkt-product-scroll-progress',
      progressFillId: 'mkt-product-scroll-fill',
      revealSelectors: '.mkt-reveal, .mkt-reveal-stagger'
    });
  }

  /* ----- Pinned product frame: update visible panel per chapter (GAP.1) ----- */
  var pinnedFrame = document.getElementById('mkt-product-pinned-frame');
  var chapterSections = root.querySelectorAll('section[data-chapter]');
  if (pinnedFrame && chapterSections.length > 0) {
    var activeChapter = 1;
    var chapterObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var ch = entry.target.getAttribute('data-chapter');
          if (ch) {
            var n = parseInt(ch, 10);
            if (!isNaN(n) && n >= 1 && n <= 6) {
              activeChapter = n;
              setPinnedFrameChapter(pinnedFrame, activeChapter);
            }
          }
        });
      },
      { root: null, rootMargin: '-15% 0px -60% 0px', threshold: 0 }
    );
    chapterSections.forEach(function (section) {
      chapterObserver.observe(section);
    });
    setPinnedFrameChapter(pinnedFrame, 1);
  }

  function setPinnedFrameChapter(frame, chapter) {
    var panels = frame.querySelectorAll('.mkt-product-pinned-panel');
    panels.forEach(function (panel) {
      var panelChapter = panel.getAttribute('data-chapter');
      if (panelChapter === String(chapter)) {
        panel.classList.add('active');
        panel.setAttribute('aria-hidden', 'false');
      } else {
        panel.classList.remove('active');
        panel.setAttribute('aria-hidden', 'true');
      }
    });
    frame.setAttribute('data-active-chapter', String(chapter));
  }
})();
