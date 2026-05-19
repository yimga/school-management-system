/**
 * Marketing lane chrome — shifts header/footer accent by active route family.
 */
(function () {
  'use strict';

  function resolveLane(path) {
    if (!path) return 'home';
    if (/\/teach\/academics|\/platform\/student-information|\/academics\/?/i.test(path)) return 'academics';
    if (/\/run\/admissions|\/platform\/admissions|\/admissions\/?/i.test(path)) return 'admissions';
    if (/\/pay\/fees|\/platform\/fees|\/roles\/finance|\/finance\/?/i.test(path)) return 'finance';
    return 'home';
  }

  var LANE_PERSONALITY = {
    academics: 'lane-academics',
    admissions: 'lane-admissions',
    finance: 'lane-finance',
    home: 'home',
  };

  function boot() {
    var lane = resolveLane(window.location.pathname || '');
    document.documentElement.setAttribute('data-mkt-lane', lane);
    if (!document.documentElement.getAttribute('data-mkt-personality')) {
      var personality = LANE_PERSONALITY[lane] || lane;
      if (personality) {
        document.documentElement.setAttribute('data-mkt-personality', personality);
      }
    }
    document.querySelectorAll('.mkt-navbar, .mkt-footer').forEach(function (node) {
      node.setAttribute('data-mkt-lane-accent', lane);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
