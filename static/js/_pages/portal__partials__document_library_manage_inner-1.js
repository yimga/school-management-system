(function(){
  var pageDataEl=document.getElementById("page-data-portal__partials__document_library_manage_inner-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["portal__partials__document_library_manage_inner-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function () {
  var DELETE_URL_TEMPLATE = ((window.__RMC_PAGE_DATA__["portal__partials__document_library_manage_inner-1"] || {})["url_portal_document_delete"]);
  function confirmDelete(docId, docTitle) {
    var t = document.getElementById('deleteDocTitle');
    if (t) t.textContent = docTitle || '';
    var f = document.getElementById('deleteForm');
    if (f) f.action = DELETE_URL_TEMPLATE.replace('999999', String(docId));
    var m = document.getElementById('deleteModal');
    if (m && window.bootstrap) new bootstrap.Modal(m).show();
  }
  document.querySelectorAll('.doc-library-page button[data-doc-id]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      confirmDelete(btn.getAttribute('data-doc-id'), btn.getAttribute('data-doc-title'));
    });
  });
})();
})();
