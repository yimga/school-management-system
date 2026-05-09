(function(){
  var pageDataEl=document.getElementById("page-data-accounts__migration_wizard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["accounts__migration_wizard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var schemaHints = (window.__RMC_PAGE_DATA__["accounts__migration_wizard-1"]||{})["var_schema_hints_json_safe"];
  if (typeof schemaHints !== 'object') schemaHints = {};
  var selects = document.querySelectorAll('.map-select');
  selects.forEach(function(s) {
    var header = s.getAttribute('data-header');
    var suggested = header && schemaHints[header];
    if (suggested && s.querySelector('option[value="' + suggested + '"]')) {
      s.value = suggested;
    }
  });
  var runForm = document.getElementById('run-form');
  var runFormCommit = document.getElementById('run-form-commit');
  var mappingInput = document.getElementById('mapping-input');
  var mappingInputCommit = document.getElementById('mapping-input-commit');
  function buildMapping() {
    var m = {};
    selects.forEach(function(s) {
      var header = s.getAttribute('data-header');
      var val = s.value;
      if (header && val) m[header] = val;
    });
    var json = JSON.stringify(m);
    if (mappingInput) mappingInput.value = json;
    if (mappingInputCommit) mappingInputCommit.value = json;
  }
  selects.forEach(function(s) { s.addEventListener('change', buildMapping); });
  if (runForm) runForm.addEventListener('submit', function() { buildMapping(); });
  if (runFormCommit) runFormCommit.addEventListener('submit', function() { buildMapping(); });
})();
})();
