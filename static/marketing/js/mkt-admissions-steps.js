/**
 * Admissions lane interactive step list.
 */
(function () {
  'use strict';

  function init(root) {
    if (!root) return;
    var steps = root.querySelectorAll('.mkt-lane-admissions__step');
    if (!steps.length) return;

    function activate(stepEl) {
      steps.forEach(function (step) {
        var on = step === stepEl;
        step.classList.toggle('is-active', on);
        var btn = step.querySelector('.mkt-lane-admissions__step-btn');
        var detail = step.querySelector('.mkt-lane-admissions__detail');
        if (btn) btn.setAttribute('aria-expanded', on ? 'true' : 'false');
        if (detail) detail.hidden = !on;
      });
    }

    steps.forEach(function (step) {
      var btn = step.querySelector('.mkt-lane-admissions__step-btn');
      if (!btn) return;
      btn.addEventListener('click', function () {
        activate(step);
      });
    });
  }

  function boot() {
    document.querySelectorAll('[data-mkt-admissions-steps]').forEach(init);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
