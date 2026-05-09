(function(){
  var pageDataEl=document.getElementById("page-data-marketplace__partials__install_impact_modal-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function () {
  var boot = document.getElementById("rmc-install-impact-boot");
  var previewBase = boot ? boot.getAttribute("data-preview-url") || "" : "";
  var superNeedsSchool = boot && boot.getAttribute("data-needs-school") === "1";
  var modalEl = document.getElementById("rmcInstallImpactModal");
  var bodyEl = document.getElementById("rmcInstallImpactBody");
  var appInput = document.getElementById("rmcInstallImpactAppId");
  var schoolInput = document.getElementById("rmcInstallImpactSchoolId");
  var confirmBtn = document.getElementById("rmcInstallImpactConfirmBtn");
  function esc(s) {
    if (s == null) return "";
    var d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }
  function renderImpact(d) {
    if (d.error) {
      bodyEl.innerHTML = "<p class=\"text-danger\">" + esc(d.error) + "</p>";
      confirmBtn.disabled = true;
      return;
    }
    var html = "";
    html += "<h3 class=\"h6\">" + esc(d.app && d.app.name) + "</h3>";
    html += "<p class=\"text-muted\">" + esc(d.app && d.app.slug) + " · v" + esc(d.app && d.app.version) + "</p>";
    var comp = d.compatibility || {};
    if (comp.errors && comp.errors.length) {
      html += "<div class=\"alert alert-danger\"><strong>(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_compatibility"]:</strong><ul class=\"mb-0\">";
      comp.errors.forEach(function (e) { html += "<li>" + esc(e) + "</li>"; });
      html += "</ul></div>";
    }
    if (comp.warnings && comp.warnings.length) {
      html += "<div class=\"alert alert-warning\"><strong>(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_warnings"]:</strong><ul class=\"mb-0\">";
      comp.warnings.forEach(function (w) { html += "<li>" + esc(w) + "</li>"; });
      html += "</ul></div>";
    }
    var ent = d.entitlement || {};
    if (ent.blocked) {
      html += "<div class=\"alert alert-warning\" data-rmc-mkt-plan-gate=\"1\"><strong>(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_plan_modules"]:</strong> " + esc(ent.upgrade_message || "") + "</div>";
    }
    html += "<h4 class=\"h6 mt-3\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_scopes"]</h4><ul class=\"list-unstyled\">";
    (d.scopes || []).forEach(function (s) {
      html += "<li><code>" + esc(s.scope_code) + "</code>";
      if (s.sensitive) html += " <span class=\"badge text-bg-warning\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_sensitive"]</span>";
      html += "</li>";
    });
    html += "</ul>";
    var prev = d.package_impact_preview;
    if (prev && prev.impacted_artifacts) {
      html += "<h4 class=\"h6 mt-3\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_metadata_package_impact"]</h4>";
      var sections = prev.impacted_artifacts.sections || [];
      html += "<p class=\"mb-1\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_sections"]: " + esc(sections.join(", ")) + "</p>";
      if (prev.warnings && prev.warnings.length) {
        html += "<p class=\"text-warning mb-0\">" + esc(prev.warnings.join("; ")) + "</p>";
      }
    } else if (d.installed_impact_summary && Object.keys(d.installed_impact_summary).length) {
      html += "<h4 class=\"h6 mt-3\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_prior_install_impact_stored"]</h4>";
      html += "<pre class=\"small bg-light p-2 rounded\">" + esc(JSON.stringify(d.installed_impact_summary, null, 2)) + "</pre>";
    } else {
      html += "<p class=\"text-muted mt-3 mb-0\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_no_package_payload_registered_for_this_app_slug_scope_list_defines_api_access_register_packageversion_to_enable_full_impact_diff"]</p>";
    }
    html += "<h4 class=\"h6 mt-3\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_dependency_graph"]</h4>";
    html += "<p class=\"small text-muted mb-1\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_pan_by_dragging_zoom_with_the_mouse_wheel"]</p>";
    html += "<div id=\"rmcInstallImpactGraph\" class=\"border rounded bg-white\" style=\"min-height:200px;\"></div>";
    var rb = (d.rollback && d.rollback.sandbox) || "";
    html += "<p class=\"mt-3 small text-muted mb-0\"><strong>(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_rollback"]:</strong> " + esc(rb) + "</p>";
    bodyEl.innerHTML = html;
    var dg = d.dependency_graph || {};
    var center =
      (d.package_resolution && d.package_resolution.matched_package_id) ||
      (d.app && d.app.slug) ||
      "package";
    var gel = document.getElementById("rmcInstallImpactGraph");
    if (gel && window.RmcPackageDependencyGraph) {
      window.RmcPackageDependencyGraph.render(gel, {
        center_id: center,
        upstream_package_ids: dg.upstream_package_ids || [],
        downstream_package_ids: dg.downstream_package_ids || [],
      });
    }
    confirmBtn.disabled = !!(comp.errors && comp.errors.length) || !!ent.blocked;
  }
  function loadImpact(appId, schoolId) {
    bodyEl.innerHTML = "<div class=\"spinner-border spinner-border-sm\"></div>";
    confirmBtn.disabled = true;
    appInput.value = appId;
    schoolInput.value = schoolId || "";
    var sep = previewBase.indexOf("?") >= 0 ? "&" : "?";
    var url = previewBase + sep + "app_id=" + encodeURIComponent(appId);
    if (schoolId) url += "&school_id=" + encodeURIComponent(schoolId);
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (x) { renderImpact(x.j); })
      .catch(function () {
        bodyEl.innerHTML = "<p class=\"text-danger\">(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_could_not_load_preview"]</p>";
        confirmBtn.disabled = true;
      });
  }
  document.querySelectorAll("[data-rmc-open-install-impact]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var appId = btn.getAttribute("data-app-id");
      var row = btn.closest("[data-rmc-school-select]");
      var sel = row ? row.querySelector("select[name=\"school_id\"]") : null;
      var schoolId = btn.getAttribute("data-school-id") || (sel && sel.value) || "";
      if (superNeedsSchool && !schoolId) {
        alert("(window.__RMC_PAGE_DATA__["marketplace__partials__install_impact_modal-1"]||{})["trans_select_a_school_first_then_preview_impact"]");
        return;
      }
      if (!modalEl || typeof bootstrap === "undefined") return;
      new bootstrap.Modal(modalEl).show();
      loadImpact(appId, schoolId);
    });
  });
})();
})();
