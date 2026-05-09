    document.addEventListener('DOMContentLoaded', function () {
      if (!window.rmcClickTaskBoundary) return;
      window.rmcClickTaskBoundary('task_start', 'marketplace_install');
      var root = document.querySelector('[data-task="marketplace_install"]');
      if (!root) return;
      root.addEventListener('submit', function (ev) {
        var form = ev.target;
        if (!form || !form.getAttribute || !form.getAttribute('action')) return;
        if (form.getAttribute('action').indexOf('activate') === -1) return;
        window.rmcClickTaskBoundary('task_complete', 'marketplace_install');
      }, true);
    });
  
