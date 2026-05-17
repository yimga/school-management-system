(function(){
  var pageDataEl=document.getElementById("page-data-studio_os__partials__launch_school_infrastructure_body-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["studio_os__partials__launch_school_infrastructure_body-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function () {
  var sel = document.getElementById('studio-infra-template');
  var btn = document.getElementById('studio-infra-preview-btn');
  var statusEl = document.getElementById('studio-infra-status');
  var box = document.getElementById('studio-infra-result');
  var sum = document.getElementById('studio-infra-summary');
  var diffBody = document.querySelector('#studio-infra-diff tbody');
  var rbNote = document.getElementById('studio-infra-rollback-note');
  var apNote = document.getElementById('studio-infra-apply-note');
  var previewUrl = ((window.__RMC_PAGE_DATA__["studio_os__partials__launch_school_infrastructure_body-1"] || {})["url_studio_os_school_infrastructure_preview_api"]);
  if (!btn || !sel) return;
  btn.addEventListener('click', function () {
    var key = (sel.value || '').trim();
    if (!key) return;
    statusEl.textContent = '…';
    sum.innerHTML = '';
    diffBody.innerHTML = '';
    box.hidden = false;
    fetch(previewUrl + '?template=' + encodeURIComponent(key), { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        statusEl.textContent = data.ok ? 'OK' : 'Review warnings';
        var wf = (data.resolved_workflow_packs || []).length;
        var db = (data.resolved_dashboard_packs || []).length;
        var th = (data.resolved_theme_packs || []).length;
        var li = document.createElement('li');
        li.textContent = 'Workflow packs: ' + wf + ' · Dashboard packs: ' + db + ' · Theme packs: ' + th;
        sum.appendChild(li);
        if (data.install_preview && data.install_preview.label) {
          var ip = document.createElement('li');
          ip.className = 'text-muted';
          ip.textContent = data.install_preview.label + (data.install_preview.catalog_resolves_cleanly ? '' : ' (see unresolved)');
          sum.appendChild(ip);
        }
        if ((data.unresolved_pack_keys || []).length) {
          var u = document.createElement('li');
          u.className = 'text-warning';
          u.textContent = 'Unresolved: ' + data.unresolved_pack_keys.join(', ');
          sum.appendChild(u);
        }
        if ((data.catalog_warnings || []).length) {
          data.catalog_warnings.forEach(function (w) {
            var wli = document.createElement('li');
            wli.className = 'text-warning';
            wli.textContent = w;
            sum.appendChild(wli);
          });
        }
        (data.diff_rows || []).forEach(function (row) {
          var tr = document.createElement('tr');
          tr.innerHTML = '<td>' + (row.aspect || '') + '</td><td>' + (row.before || '') + '</td><td>' + (row.after || '') + '</td>';
          diffBody.appendChild(tr);
        });
        rbNote.textContent = data.rollback_supported
          ? ((window.__RMC_PAGE_DATA__["studio_os__partials__launch_school_infrastructure_body-1"] || {})["trans_rollback_is_flagged_as_supported_for_this_template_platform_governed"])
          : ((window.__RMC_PAGE_DATA__["studio_os__partials__launch_school_infrastructure_body-1"] || {})["trans_rollback_disabled_for_tenant_apply_use_platform_rollback_when_available"]);
        apNote.textContent = data.tenant_safe_apply
          ? ((window.__RMC_PAGE_DATA__["studio_os__partials__launch_school_infrastructure_body-1"] || {})["trans_tenant_apply_may_be_supported_for_this_template_in_future_releases"])
          : ((window.__RMC_PAGE_DATA__["studio_os__partials__launch_school_infrastructure_body-1"] || {})["trans_one_click_tenant_apply_is_not_enabled_request_changes_via_your_platform_administrator"]);
      })
      .catch(function () {
        statusEl.textContent = 'Error';
      });
  });
})();
})();
