  document.addEventListener('DOMContentLoaded', function () {
    if (!window.rmcClickTaskBoundary) return;
    window.rmcClickTaskBoundary('task_start', 'attendance_export');
    var f = document.getElementById('rmc-attendance-export-form');
    if (f) {
      f.addEventListener('submit', function () {
        window.rmcClickTaskBoundary('task_complete', 'attendance_export');
      });
    }
  });
