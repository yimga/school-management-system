(function() {
  var form = document.getElementById('access-request-form');
  var btn = document.getElementById('access-request-btn');
  if (form && btn) {
    form.addEventListener('submit', function() {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Submitting…';
    });
  }
  if (form && window.FormDraftSave) window.FormDraftSave.init(form);
})();
