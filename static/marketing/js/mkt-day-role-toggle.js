/**
 * Homepage day-of-week vs role story toggle.
 */
(function () {
  'use strict';

  function init(root) {
    if (!root) return;
    var tabs = root.querySelectorAll('[data-day-role-tab]');
    var panels = root.querySelectorAll('[data-day-role-panel]');
    if (!tabs.length) return;

    function show(mode) {
      tabs.forEach(function (tab) {
        var on = tab.getAttribute('data-day-role-tab') === mode;
        tab.setAttribute('aria-selected', on ? 'true' : 'false');
        tab.tabIndex = on ? 0 : -1;
      });
      panels.forEach(function (panel) {
        var on = panel.getAttribute('data-day-role-panel') === mode;
        panel.hidden = !on;
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        show(tab.getAttribute('data-day-role-tab'));
      });
      tab.addEventListener('keydown', function (ev) {
        if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
        ev.preventDefault();
        var list = Array.prototype.slice.call(tabs);
        var i = list.indexOf(tab);
        var next = ev.key === 'ArrowRight' ? (i + 1) % list.length : (i - 1 + list.length) % list.length;
        list[next].focus();
        show(list[next].getAttribute('data-day-role-tab'));
      });
    });

    show('time');
  }

  function boot() {
    document.querySelectorAll('[data-mkt-day-role]').forEach(init);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
