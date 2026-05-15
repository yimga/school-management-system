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
  var consentListEl = document.getElementById("rmcInstallImpactConsentList");
  var consentStatusEl = document.getElementById("rmcInstallImpactConsentStatus");
  var pageData = (window.__RMC_PAGE_DATA__ || {})["marketplace__partials__install_impact_modal-1"] || {};
  var hasBlockingState = false;
  function _t(key) { return pageData[key] || key; }
  function refreshConsentGate() {
    if (!consentListEl) return;
    var boxes = consentListEl.querySelectorAll('input[type="checkbox"][name="consented_scopes"]');
    var total = boxes.length;
    var checked = 0;
    for (var i = 0; i < boxes.length; i++) { if (boxes[i].checked) checked++; }
    var allOk = total === 0 || checked === total;
    if (consentStatusEl) {
      if (total === 0) {
        consentStatusEl.textContent = _t("trans_consent_no_scopes");
      } else if (allOk) {
        consentStatusEl.textContent = _t("trans_consent_complete");
      } else {
        var remaining = total - checked;
        consentStatusEl.textContent = (_t("trans_consent_required_n_remaining") || "").replace("{n}", String(remaining));
      }
    }
    confirmBtn.disabled = hasBlockingState || !allOk;
  }
  function renderConsent(scopes) {
    if (!consentListEl) return;
    consentListEl.innerHTML = "";
    (scopes || []).forEach(function (s, idx) {
      var code = (s && s.scope_code) || "";
      if (!code) return;
      var id = "rmc-consent-" + idx + "-" + code.replace(/[^a-z0-9_-]/gi, "-");
      var wrapper = document.createElement("label");
      wrapper.className = "rmc-scope-consent__item" + (s.sensitive ? " is-sensitive" : "");
      wrapper.setAttribute("for", id);
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.name = "consented_scopes";
      cb.value = code;
      cb.id = id;
      cb.required = true;
      cb.className = "rmc-scope-consent__checkbox";
      cb.addEventListener("change", refreshConsentGate);
      var codeSpan = document.createElement("code");
      codeSpan.className = "rmc-scope-consent__code";
      codeSpan.textContent = code;
      wrapper.appendChild(cb);
      wrapper.appendChild(codeSpan);
      if (s.description) {
        var desc = document.createElement("span");
        desc.className = "rmc-scope-consent__desc";
        desc.textContent = " — " + s.description;
        wrapper.appendChild(desc);
      }
      if (s.sensitive) {
        var badge = document.createElement("span");
        badge.className = "badge text-bg-warning rmc-scope-consent__badge";
        badge.textContent = _t("trans_sensitive");
        wrapper.appendChild(badge);
      }
      consentListEl.appendChild(wrapper);
    });
    refreshConsentGate();
  }
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
      html += "<div class=\"alert alert-danger\"><strong>" + esc(_t("trans_compatibility")) + ":</strong><ul class=\"mb-0\">";
      comp.errors.forEach(function (e) { html += "<li>" + esc(e) + "</li>"; });
      html += "</ul></div>";
    }
    if (comp.warnings && comp.warnings.length) {
      html += "<div class=\"alert alert-warning\"><strong>" + esc(_t("trans_warnings")) + ":</strong><ul class=\"mb-0\">";
      comp.warnings.forEach(function (w) { html += "<li>" + esc(w) + "</li>"; });
      html += "</ul></div>";
    }
    var ent = d.entitlement || {};
    if (ent.blocked) {
      html += "<div class=\"alert alert-warning\" data-rmc-mkt-plan-gate=\"1\"><strong>" + esc(_t("trans_plan_modules")) + ":</strong> " + esc(ent.upgrade_message || "") + "</div>";
    }
    html += "<h4 class=\"h6 mt-3\">" + esc(_t("trans_scopes")) + "</h4>";
    html += "<p class=\"text-muted small mb-2\">" + esc(_t("trans_consent_required_label")) + "</p>";
    var prev = d.package_impact_preview;
    if (prev && prev.impacted_artifacts) {
      html += "<h4 class=\"h6 mt-3\">" + esc(_t("trans_metadata_package_impact")) + "</h4>";
      var sections = prev.impacted_artifacts.sections || [];
      html += "<p class=\"mb-1\">" + esc(_t("trans_sections")) + ": " + esc(sections.join(", ")) + "</p>";
      if (prev.warnings && prev.warnings.length) {
        html += "<p class=\"text-warning mb-0\">" + esc(prev.warnings.join("; ")) + "</p>";
      }
    } else if (d.installed_impact_summary && Object.keys(d.installed_impact_summary).length) {
      html += "<h4 class=\"h6 mt-3\">" + esc(_t("trans_prior_install_impact_stored")) + "</h4>";
      html += "<pre class=\"small bg-light p-2 rounded\">" + esc(JSON.stringify(d.installed_impact_summary, null, 2)) + "</pre>";
    } else {
      html += "<p class=\"text-muted mt-3 mb-0\">" + esc(_t("trans_no_package_payload_registered_for_this_app_slug_scope_list_defines_api_access_register_packageversion_to_enable_full_impact_diff")) + "</p>";
    }
    html += "<h4 class=\"h6 mt-3\">" + esc(_t("trans_dependency_graph")) + "</h4>";
    html += "<p class=\"small text-muted mb-1\">" + esc(_t("trans_pan_by_dragging_zoom_with_the_mouse_wheel")) + "</p>";
    html += "<div id=\"rmcInstallImpactGraph\" class=\"border rounded bg-white rmc-install-impact-graph\"></div>";
    var rb = (d.rollback && d.rollback.sandbox) || "";
    html += "<p class=\"mt-3 small text-muted mb-0\"><strong>" + esc(_t("trans_rollback")) + ":</strong> " + esc(rb) + "</p>";
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
    hasBlockingState = !!(comp.errors && comp.errors.length) || !!ent.blocked;
    renderConsent(d.scopes || []);
    refreshConsentGate();
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
        bodyEl.innerHTML = "<p class=\"text-danger\">" + esc(_t("trans_could_not_load_preview")) + "</p>";
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
        alert("" + esc(_t("trans_select_a_school_first_then_preview_impact")) + "");
        return;
      }
      if (!modalEl || typeof bootstrap === "undefined") return;
      new bootstrap.Modal(modalEl).show();
      loadImpact(appId, schoolId);
    });
  });
})();
})();
