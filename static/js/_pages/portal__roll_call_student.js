  document.addEventListener('DOMContentLoaded', function() {
    var f = document.querySelector('form[data-draft-key][method="post"]');
    if (f && window.FormDraftSave) window.FormDraftSave.init(f);
  });
  
