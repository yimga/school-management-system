  document.addEventListener('DOMContentLoaded', function () {
    if (!window.rmcClickTaskBoundary) return;
    window.rmcClickTaskBoundary('task_start', 'report_generation');
    var pf = document.getElementById('rmc-publish-term-form');
    if (pf) {
      pf.addEventListener('submit', function () {
        window.rmcClickTaskBoundary('task_complete', 'report_generation');
      });
    }
  });
