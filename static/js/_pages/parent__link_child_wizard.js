// link-child-wizard form bootstrap. Reads the focus-target field id from a
// JSON data island so the inline executable script can be removed.
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('link-child-wizard-form');
    if (form && window.FormDraftSave) window.FormDraftSave.init(form);

    var el = document.getElementById('link-child-wizard-config');
    var cfg = {};
    if (el) {
      try { cfg = JSON.parse(el.textContent || '{}'); } catch (_e) { cfg = {}; }
    }
    if (cfg.step === 1 && cfg.admissionFieldId) {
      var admissionField = document.getElementById(cfg.admissionFieldId);
      if (admissionField) admissionField.focus();
    }

    // Ctrl+Enter inside textareas submits the form (preserves prior behavior).
    document.querySelectorAll('textarea').forEach(function (textarea) {
      textarea.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.ctrlKey) {
          e.preventDefault();
          if (form) form.submit();
        }
      });
    });
  });
})();
