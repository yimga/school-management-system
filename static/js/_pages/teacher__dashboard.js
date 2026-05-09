  (function () {
    var apply = function () {
      if (!document.body) return;
      document.body.dataset.dashboardPage = 'teacher';
      document.body.classList.add('dashboard-page-teacher');
    };
    apply();
    document.addEventListener('DOMContentLoaded', apply, { once: true });
  })();
  document.documentElement.classList.add('tdm-mounted');
