(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var wide = document.querySelector('.backend-bento-chart-wide');
    var panel = document.getElementById('backendBentoDrillPanel');
    if (!wide || !panel) return;
    function toggle() {
      var open = !panel.classList.contains('d-none');
      panel.classList.toggle('d-none', open);
      wide.classList.toggle('is-expanded', !open);
      wide.setAttribute('aria-expanded', open ? 'false' : 'true');
      if (!open) {
        panel.setAttribute('tabindex', '-1');
        try {
          panel.focus({ preventScroll: true });
        } catch (e) {
          panel.focus();
        }
      }
    }
    wide.setAttribute('role', 'button');
    wide.setAttribute('tabindex', '0');
    wide.setAttribute('aria-expanded', 'false');
    wide.addEventListener('click', function (e) {
      if (e.target.closest('a')) return;
      toggle();
    });
    wide.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggle();
      }
    });
  });
})();
