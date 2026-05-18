(function(){
  var pageDataEl=document.getElementById("page-data-accounts__institution_profile_wizard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["accounts__institution_profile_wizard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  (function(){
    var u = ((window.__RMC_PAGE_DATA__["accounts__institution_profile_wizard-1"] || {})["var_suggest_url_escapejs"]);
    document.getElementById("btnInstSuggest")?.addEventListener("click", function(){
      fetch(u, {credentials:"same-origin"}).then(function(r){return r.json()}).then(function(d){
        var o = document.getElementById("instSuggestOut");
        o.textContent = JSON.stringify(d, null, 2);
        o.classList.remove("d-none");
      }).catch(function(e){ alert(e); });
    });
  })();
  
})();
