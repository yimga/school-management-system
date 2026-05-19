/**
 * Bell-clock sticky sync + persona tab panels (IntersectionObserver, no deps).
 */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function initBellClock(root) {
    if (!root) return;
    var steps = root.querySelectorAll('[data-bell-step]');
    var panels = root.querySelectorAll('[data-bell-panel]');
    var singleMode = root.getAttribute('data-mkt-bell-clock-mode') === 'single';
    var storyMetric = root.querySelector('[data-bell-story-metric]');
    var storyLabel = root.querySelector('[data-bell-story-label]');
    if (!steps.length || !panels.length) return;

    function syncStory(stepEl) {
      if (!stepEl) return;
      if (storyMetric && stepEl.getAttribute('data-bell-metric')) {
        storyMetric.textContent = stepEl.getAttribute('data-bell-metric');
      }
      if (storyLabel && stepEl.getAttribute('data-bell-story')) {
        storyLabel.textContent = stepEl.getAttribute('data-bell-story');
      }
    }

    function setActive(index) {
      var activeStep = steps[index];
      steps.forEach(function (step, i) {
        var on = i === index;
        step.classList.toggle('is-active', on);
        step.setAttribute('aria-current', on ? 'step' : 'false');
      });
      syncStory(activeStep);

      if (singleMode && !reduced) {
        panels.forEach(function (panel, i) {
          var on = i === index;
          panel.classList.toggle('is-active', on);
          panel.hidden = !on;
        });
        return;
      }

      if (!reduced) {
        panels.forEach(function (panel, i) {
          panel.hidden = i !== index;
          panel.classList.toggle('is-active', i === index);
        });
      }
    }

    setActive(0);

    steps.forEach(function (step, stepIndex) {
      step.addEventListener('click', function () {
        var idx = parseInt(step.getAttribute('data-bell-step'), 10);
        if (!isNaN(idx)) setActive(idx);
      });
      step.addEventListener('keydown', function (ev) {
        var list = Array.prototype.slice.call(steps);
        var i = list.indexOf(step);
        if (ev.key === 'ArrowRight' || ev.key === 'ArrowDown') {
          ev.preventDefault();
          var next = (i + 1) % list.length;
          setActive(next);
          list[next].focus();
        }
        if (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp') {
          ev.preventDefault();
          var prev = (i - 1 + list.length) % list.length;
          setActive(prev);
          list[prev].focus();
        }
        if (ev.key === 'Home') {
          ev.preventDefault();
          setActive(0);
          list[0].focus();
        }
        if (ev.key === 'End') {
          ev.preventDefault();
          setActive(list.length - 1);
          list[list.length - 1].focus();
        }
      });
      if (!step.hasAttribute('tabindex')) {
        step.setAttribute('tabindex', stepIndex === 0 ? '0' : '-1');
      }
    });

    var autoMs = parseInt(root.getAttribute('data-bell-auto-ms'), 10);
    if (autoMs > 0 && !reduced && singleMode) {
      var autoTimer = null;
      function startAuto() {
        if (autoTimer) clearInterval(autoTimer);
        autoTimer = setInterval(function () {
          var current = 0;
          steps.forEach(function (step, i) {
            if (step.classList.contains('is-active')) current = i;
          });
          setActive((current + 1) % steps.length);
        }, autoMs);
      }
      function stopAuto() {
        if (autoTimer) {
          clearInterval(autoTimer);
          autoTimer = null;
        }
      }
      startAuto();
      root.addEventListener('mouseenter', stopAuto);
      root.addEventListener('mouseleave', startAuto);
      root.addEventListener('focusin', stopAuto);
      root.addEventListener('focusout', function (ev) {
        if (!root.contains(ev.relatedTarget)) startAuto();
      });
    }

    if (reduced || typeof IntersectionObserver === 'undefined') return;

    if (singleMode) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var idx = parseInt(entry.target.getAttribute('data-bell-step'), 10);
            if (!isNaN(idx)) setActive(idx);
          });
        },
        { rootMargin: '-40% 0px -50% 0px', threshold: 0.15 }
      );
      steps.forEach(function (step) { observer.observe(step); });
      return;
    }

    var panelObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var idx = parseInt(entry.target.getAttribute('data-bell-panel'), 10);
          if (!isNaN(idx)) setActive(idx);
        });
      },
      { rootMargin: '-35% 0px -45% 0px', threshold: 0.2 }
    );

    panels.forEach(function (panel) { panelObserver.observe(panel); });
  }

  function initPersonaTabs(root) {
    if (!root) return;
    var buttons = root.querySelectorAll('[data-persona-tab]');
    var panels = root.querySelectorAll('[data-persona-panel]');
    var metricValue = root.querySelector('[data-persona-metric-value]');
    var metricLabel = root.querySelector('[data-persona-metric-label]');
    if (!buttons.length || !panels.length) return;

    function activate(id) {
      var activeBtn = null;
      buttons.forEach(function (btn) {
        var on = btn.getAttribute('data-persona-tab') === id;
        if (on) activeBtn = btn;
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
        btn.tabIndex = on ? 0 : -1;
      });
      panels.forEach(function (panel) {
        panel.hidden = panel.getAttribute('data-persona-panel') !== id;
      });
      if (activeBtn) {
        if (metricValue && activeBtn.getAttribute('data-persona-metric')) {
          metricValue.textContent = activeBtn.getAttribute('data-persona-metric');
        }
        if (metricLabel && activeBtn.getAttribute('data-persona-metric-label')) {
          metricLabel.textContent = activeBtn.getAttribute('data-persona-metric-label');
        }
      }
    }

    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        activate(btn.getAttribute('data-persona-tab'));
      });
      btn.addEventListener('keydown', function (ev) {
        var list = Array.prototype.slice.call(buttons);
        var i = list.indexOf(btn);
        if (ev.key === 'ArrowRight' || ev.key === 'ArrowDown') {
          ev.preventDefault();
          list[(i + 1) % list.length].focus();
        }
        if (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp') {
          ev.preventDefault();
          list[(i - 1 + list.length) % list.length].focus();
        }
      });
    });

    activate(buttons[0].getAttribute('data-persona-tab'));
  }

  function initParallax() {
    if (reduced) return;
    var nodes = document.querySelectorAll('[data-mkt-parallax]');
    if (!nodes.length) return;
    var factor = 0.06;
    window.addEventListener(
      'scroll',
      function () {
        var y = window.scrollY || 0;
        nodes.forEach(function (node) {
          var f = parseFloat(node.getAttribute('data-mkt-parallax')) || factor;
          node.style.transform = 'translate3d(0, ' + Math.round(y * f) + 'px, 0)';
        });
      },
      { passive: true }
    );
  }

  function initModuleRail(root) {
    if (!root) return;
    var links = root.querySelectorAll('[data-module-link]');
    var panels = root.querySelectorAll('[data-module-panel]');
    if (!links.length || !panels.length) return;

    function activate(slug) {
      links.forEach(function (link) {
        var on = link.getAttribute('data-module-link') === slug;
        link.classList.toggle('is-active', on);
      });
      if (!reduced) {
        panels.forEach(function (panel) {
          panel.hidden = panel.getAttribute('data-module-panel') !== slug;
        });
      }
    }

    links.forEach(function (link) {
      link.addEventListener('click', function (ev) {
        ev.preventDefault();
        activate(link.getAttribute('data-module-link'));
        var target = root.querySelector('#module-' + link.getAttribute('data-module-link'));
        if (target) target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
      });
    });

    if (typeof IntersectionObserver !== 'undefined' && !reduced) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            activate(entry.target.getAttribute('data-module-panel'));
          });
        },
        { rootMargin: '-35% 0px -45% 0px', threshold: 0.2 }
      );
      panels.forEach(function (panel) { observer.observe(panel); });
    }
  }

  function boot() {
    initBellClock(document.querySelector('[data-mkt-bell-clock]'));
    initPersonaTabs(document.querySelector('[data-mkt-persona-tabs]'));
    initModuleRail(document.querySelector('[data-mkt-module-rail]'));
    initParallax();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
