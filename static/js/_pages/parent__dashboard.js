  (function () {
    var apply = function () {
      if (!document.body) return;
      document.body.dataset.dashboardPage = 'parent';
      document.body.classList.add('dashboard-page-parent');
    };
    apply();
    document.addEventListener('DOMContentLoaded', apply, { once: true });
  })();
