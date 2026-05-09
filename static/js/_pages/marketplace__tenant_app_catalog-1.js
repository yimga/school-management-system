(function(){
  var pageDataEl=document.getElementById("page-data-marketplace__tenant_app_catalog-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["marketplace__tenant_app_catalog-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  (function () {
    document.addEventListener("DOMContentLoaded", function () {
      var id = "(window.__RMC_PAGE_DATA__["marketplace__tenant_app_catalog-1"]||{})["var_catalog_install_app_id"]";
      var btn = document.querySelector("[data-rmc-open-install-impact][data-app-id=\"" + id + "\"]");
      if (btn && !btn.disabled) {
        btn.click();
      }
    });
  })();
  
})();
