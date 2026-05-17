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
    if (!steps.length || !panels.length) return;

    function setActive(index) {
      steps.forEach(function (step, i) {
        var on = i === index;
        step.classList.toggle('is-active', on);
        step.setAttribute('aria-current', on ? 'step' : 'false');
      });
      if (!reduced) {
        panels.forEach(function (panel, i) {
          panel.hidden = i !== index;
        });
      }
    }

    setActive(0);

    if (reduced || typeof IntersectionObserver === 'undefined') return;

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var idx = parseInt(entry.target.getAttribute('data-bell-panel'), 10);
          if (!isNaN(idx)) setActive(idx);
        });
      },
      { rootMargin: '-35% 0px -45% 0px', threshold: 0.2 }
    );

    panels.forEach(function (panel) { observer.observe(panel); });
  }

  function initPersonaTabs(root) {
    if (!root) return;
    var buttons = root.querySelectorAll('[data-persona-tab]');
    var panels = root.querySelectorAll('[data-persona-panel]');
    if (!buttons.length || !panels.length) return;

    function activate(id) {
      buttons.forEach(function (btn) {
        var on = btn.getAttribute('data-persona-tab') === id;
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
        btn.tabIndex = on ? 0 : -1;
      });
      panels.forEach(function (panel) {
        panel.hidden = panel.getAttribute('data-persona-panel') !== id;
      });
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
