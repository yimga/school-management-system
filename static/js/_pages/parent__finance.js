  document.addEventListener('DOMContentLoaded', function () {
    if (!window.rmcClickTaskBoundary) return;
    window.rmcClickTaskBoundary('task_start', 'parent_payment');
    var root = document.querySelector('.report-card-print-wrapper[data-task="parent_payment"]');
    if (root) {
      root.addEventListener('click', function (ev) {
        var a = ev.target.closest && ev.target.closest('a[data-rmc-parent-pay="1"]');
        if (a) {
          window.rmcClickTaskBoundary('task_complete', 'parent_payment');
        }
      }, true);
    }
  });
