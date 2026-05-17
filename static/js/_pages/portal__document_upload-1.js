(function(){
  var pageDataEl=document.getElementById("page-data-portal__document_upload-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["portal__document_upload-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
// Show/hide file/link fields based on document type
document.addEventListener('DOMContentLoaded', function() {
  const docTypeField = document.getElementById(((window.__RMC_PAGE_DATA__["portal__document_upload-1"] || {})["var_form_document_type_id_for_label"]));
  const requiresSigField = document.getElementById(((window.__RMC_PAGE_DATA__["portal__document_upload-1"] || {})["var_form_requires_signature_id_for_label"]));
  
  function updateSignatureField() {
    const isForm = docTypeField.value === 'FORM';
    requiresSigField.disabled = !isForm;
    if (!isForm) {
      requiresSigField.checked = false;
    }
  }
  
  docTypeField.addEventListener('change', updateSignatureField);
  updateSignatureField();
});
})();
