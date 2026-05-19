/**
 * Interactive globe campus pins (homepage map section).
 */
(function () {
  'use strict';

  function init(mapRoot) {
    if (!mapRoot) return;
    var pins = mapRoot.querySelectorAll('.mkt-globe-pin__btn');
    if (!pins.length) return;

    function closeAll(except) {
      pins.forEach(function (btn) {
        if (btn === except) return;
        btn.setAttribute('aria-expanded', 'false');
        var card = mapRoot.querySelector('#' + btn.getAttribute('aria-controls'));
        if (card) card.hidden = true;
      });
    }

    pins.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var open = btn.getAttribute('aria-expanded') === 'true';
        closeAll(null);
        var card = mapRoot.querySelector('#' + btn.getAttribute('aria-controls'));
        if (!open && card) {
          btn.setAttribute('aria-expanded', 'true');
          card.hidden = false;
        }
      });
    });

    document.addEventListener('click', function (ev) {
      if (mapRoot.contains(ev.target)) return;
      closeAll(null);
    });
  }

  function boot() {
    document.querySelectorAll('.mkt-edt-globe__map--interactive').forEach(init);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
