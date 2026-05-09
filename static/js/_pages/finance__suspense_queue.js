(function() {
  if (!window.FormDraftSave) return;
  document.querySelectorAll('form.suspense-claim-form[data-draft-key]').forEach(function(f) {
    window.FormDraftSave.init(f);
  });
})();
