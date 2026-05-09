  document.addEventListener('DOMContentLoaded', function () {
    if (window.rmcClickTaskBoundary) {
      window.rmcClickTaskBoundary('task_start', 'teacher_marks_entry');
    }
    var form = document.getElementById('marks-entry-form');
    if (form && window.FormDraftSave) {
      FormDraftSave.init(form);
    }
    if (window.rmcClickTaskBoundary) {
      function completeMarksTask() {
        window.rmcClickTaskBoundary('task_complete', 'teacher_marks_entry');
      }
      if (form) {
        form.addEventListener('submit', completeMarksTask);
      }
      var ocrForm = document.getElementById('marks-ocr-apply-form');
      if (ocrForm) {
        ocrForm.addEventListener('submit', completeMarksTask);
      }
    }
  });
