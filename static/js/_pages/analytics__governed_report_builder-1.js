(function(){
  var pageDataEl=document.getElementById("page-data-analytics__governed_report_builder-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function(){
  function csrfHeader(){
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el && el.value) return el.value;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }
  var catalog = (window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"]||{})["var_governed_catalog_json_safe"];
  var RUN_MAGIC = ((window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"] || {})["var_saved_run_magic"]);
  var runUrlTpl = ((window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"] || {})["var_saved_run_url_magic_escapejs"]);
  var ds = document.getElementById('gr-dataset');
  Object.keys(catalog).sort().forEach(function(k){
    var o = document.createElement('option');
    o.value = k;
    o.textContent = catalog[k].label + ' (' + k + ')';
    ds.appendChild(o);
  });
  function parseFilters(){
    var raw = document.getElementById('gr-filters').value.trim();
    if (!raw) return {};
    var o = JSON.parse(raw);
    if (typeof o !== 'object' || o === null || Array.isArray(o)) throw new Error('Filters must be a JSON object');
    return o;
  }
  function payload(){
    var dsId = ds.value;
    var fieldsRaw = document.getElementById('gr-fields').value || '';
    var fields = fieldsRaw.split(',').map(function(s){ return s.trim(); }).filter(Boolean);
    if (!fields.length && catalog[dsId]) {
      fields = catalog[dsId].fields.slice(0, 12);
    }
    var filters = parseFilters();
    var gbRaw = document.getElementById('gr-groupby').value.trim();
    var group_by = gbRaw ? gbRaw.split(',').map(function(s){ return s.trim(); }).filter(Boolean) : null;
    var aggFn = document.getElementById('gr-agg-fn').value.trim();
    var aggField = document.getElementById('gr-agg-field').value.trim();
    var aggregate = null;
    if (group_by && group_by.length && aggFn) {
      aggregate = { fn: aggFn, field: aggField || 'id' };
    }
    return {
      dataset_id: dsId,
      fields: fields,
      filters: filters,
      group_by: group_by,
      aggregate: aggregate,
      limit: parseInt(document.getElementById('gr-limit').value, 10) || 100
    };
  }
  function refreshSaved(){
    fetch(((window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"] || {})["var_saved_list_url"]), { credentials: 'same-origin' })
      .then(function(r){ return r.json(); })
      .then(function(j){
        var sel = document.getElementById('gr-saved-list');
        sel.innerHTML = '';
        var opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = '—';
        sel.appendChild(opt0);
        (j.saved || []).forEach(function(s){
          var o = document.createElement('option');
          o.value = s.id;
          o.textContent = s.name + ' (#' + s.id + ')';
          sel.appendChild(o);
        });
      })
      .catch(function(e){ document.getElementById('gr-output').textContent = String(e); });
  }
  document.getElementById('gr-preview').addEventListener('click', function(){
    try {
      var body = JSON.stringify(payload());
      fetch(((window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"] || {})["var_preview_url"]), {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfHeader()},
        body: body
      }).then(function(r){ return r.json(); }).then(function(j){
        document.getElementById('gr-output').textContent = JSON.stringify(j, null, 2);
      }).catch(function(e){ document.getElementById('gr-output').textContent = String(e); });
    } catch (e) {
      document.getElementById('gr-output').textContent = e.message || String(e);
    }
  });
  function downloadBlob(blob, name){
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
  }
  document.getElementById('gr-export-csv').addEventListener('click', function(){
    try {
      fetch(((window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"] || {})["var_export_csv_url"]), {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfHeader()},
        body: JSON.stringify(payload())
      }).then(function(r){ return r.blob(); }).then(function(blob){ downloadBlob(blob, 'governed_export.csv'); })
      .catch(function(e){ document.getElementById('gr-output').textContent = String(e); });
    } catch (e) {
      document.getElementById('gr-output').textContent = e.message || String(e);
    }
  });
  document.getElementById('gr-export-json').addEventListener('click', function(){
    try {
      fetch(((window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"] || {})["var_export_json_url"]), {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfHeader()},
        body: JSON.stringify(payload())
      }).then(function(r){ return r.json(); }).then(function(j){
        document.getElementById('gr-output').textContent = JSON.stringify(j, null, 2);
      }).catch(function(e){ document.getElementById('gr-output').textContent = String(e); });
    } catch (e) {
      document.getElementById('gr-output').textContent = e.message || String(e);
    }
  });
  document.getElementById('gr-save').addEventListener('click', function(){
    var name = (document.getElementById('gr-save-name').value || '').trim();
    if (!name) { alert(((window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"] || {})["trans_enter_a_report_name"])); return; }
    try {
      var def = payload();
      fetch(((window.__RMC_PAGE_DATA__["analytics__governed_report_builder-1"] || {})["var_saved_save_url"]), {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfHeader()},
        body: JSON.stringify({ name: name, definition: def })
      }).then(function(r){ return r.json(); }).then(function(j){
        document.getElementById('gr-output').textContent = JSON.stringify(j, null, 2);
        refreshSaved();
      });
    } catch (e) {
      document.getElementById('gr-output').textContent = e.message || String(e);
    }
  });
  document.getElementById('gr-saved-refresh').addEventListener('click', refreshSaved);
  document.getElementById('gr-saved-run').addEventListener('click', function(){
    var id = document.getElementById('gr-saved-list').value;
    if (!id) return;
    var url = runUrlTpl.split(RUN_MAGIC).join(id);
    fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfHeader()},
      body: '{}'
    }).then(function(r){ return r.json(); }).then(function(j){
      document.getElementById('gr-output').textContent = JSON.stringify(j, null, 2);
    }).catch(function(e){ document.getElementById('gr-output').textContent = String(e); });
  });
  if (document.getElementById('gr-saved-list')) {
    refreshSaved();
  }
})();
})();
