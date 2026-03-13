/**
 * Help tooltips (S5 — save-for-later completed).
 * Elements with data-tooltip="..." show a bubble on hover/focus.
 * Optional: runmycampusTooltips.init() to enhance [data-tooltip] for keyboard and delay.
 */
(function () {
  'use strict';
  function init() {
    var triggers = document.querySelectorAll('[data-tooltip]');
    triggers.forEach(function (el) {
      if (el.getAttribute('aria-describedby')) return;
      var id = 'tooltip-' + Math.random().toString(36).slice(2, 9);
      var bubble = document.createElement('span');
      bubble.id = id;
      bubble.className = 'runmycampus-tooltip-bubble';
      bubble.setAttribute('role', 'tooltip');
      bubble.textContent = el.getAttribute('data-tooltip') || '';
      el.setAttribute('aria-describedby', id);
      el.style.position = 'relative';
      el.appendChild(bubble);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  window.runmycampusTooltips = { init: init };
})();
