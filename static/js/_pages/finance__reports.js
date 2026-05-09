(function() {
  if (!window.FormDraftSave) return;
  var p = document.getElementById('finance-reports-period-form');
  if (p) window.FormDraftSave.init(p);
  var r = document.getElementById('finance-report-request-form');
  if (r) window.FormDraftSave.init(r);
})();
