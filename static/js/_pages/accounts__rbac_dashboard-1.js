(function(){
  var pageDataEl=document.getElementById("page-data-accounts__rbac_dashboard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["accounts__rbac_dashboard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var modalEl = document.getElementById('editRoleModal');
  if (modalEl) {
    var modal = new bootstrap.Modal(modalEl);
    modal.show();
    modalEl.addEventListener('hidden.bs.modal', function() { window.location.href = ((window.__RMC_PAGE_DATA__["accounts__rbac_dashboard-1"] || {})["url_accounts_rbac"]); });
  }
})();
})();
