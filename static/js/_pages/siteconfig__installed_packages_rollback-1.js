(function(){
  var pageDataEl=document.getElementById("page-data-siteconfig__installed_packages_rollback-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["siteconfig__installed_packages_rollback-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function () {
  var base = ((window.__RMC_PAGE_DATA__["siteconfig__installed_packages_rollback-1"] || {})["var_package_impact_fetch_url_escapejs"]);
  var schoolId = ((window.__RMC_PAGE_DATA__["siteconfig__installed_packages_rollback-1"] || {})["var_school_pk"]);
  document.querySelectorAll(".rmc-rollback-graph-mount").forEach(function (mount) {
    var details = mount.closest("details");
    if (!details) return;
    details.addEventListener("toggle", function () {
      if (!details.open || mount.getAttribute("data-loaded") === "1") return;
      mount.setAttribute("data-loaded", "1");
      var pid = mount.getAttribute("data-package-id") || "";
      var sep = base.indexOf("?") >= 0 ? "&" : "?";
      var url = base + sep + "package_id=" + encodeURIComponent(pid) + "&school_id=" + encodeURIComponent(schoolId);
      fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          var dg = j.dependency_graph || {};
          if (window.RmcPackageDependencyGraph) {
            window.RmcPackageDependencyGraph.render(mount, {
              center_id: pid,
              upstream_package_ids: dg.upstream_package_ids || [],
              downstream_package_ids: dg.downstream_package_ids || [],
            });
          }
        })
        .catch(function () {
          var _msg = ((window.__RMC_PAGE_DATA__["siteconfig__installed_packages_rollback-1"] || {})["trans_could_not_load_graph"]) || "Could not load graph.";
          var _p = document.createElement("p");
          _p.className = "text-danger small p-2 mb-0";
          _p.textContent = _msg;
          mount.innerHTML = "";
          mount.appendChild(_p);
        });
    });
  });
})();
})();
