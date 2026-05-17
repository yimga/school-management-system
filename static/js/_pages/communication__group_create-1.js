(function(){
  var pageDataEl=document.getElementById("page-data-communication__group_create-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["communication__group_create-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
document.addEventListener('DOMContentLoaded', function() {
  const scopeSelect = document.getElementById(((window.__RMC_PAGE_DATA__["communication__group_create-1"] || {})["var_form_scope_id_for_label"]));
  const departmentField = document.getElementById('department-field');
  const classroomField = document.getElementById('classroom-field');
  
  function toggleFields() {
    const scope = scopeSelect.value;
    if (scope === 'DEPARTMENT') {
      departmentField.style.display = 'block';
      classroomField.style.display = 'none';
    } else if (scope === 'CLASSROOM') {
      departmentField.style.display = 'none';
      classroomField.style.display = 'block';
    } else {
      departmentField.style.display = 'none';
      classroomField.style.display = 'none';
    }
  }
  
  scopeSelect.addEventListener('change', toggleFields);
  toggleFields(); // Initial state
});
})();
