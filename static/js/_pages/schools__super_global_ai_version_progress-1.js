(function(){
  var pageDataEl=document.getElementById("page-data-schools__super_global_ai_version_progress-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["schools__super_global_ai_version_progress-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  (function() {
    var runId = "(window.__RMC_PAGE_DATA__["schools__super_global_ai_version_progress-1"]||{})["var_run_id_escapejs"]";
    var progressUrl = "?json=1";
    function poll() {
      fetch(window.location.pathname + progressUrl)
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var total = data.regions_total || 0;
          var done = data.regions_done !== undefined ? data.regions_done : 0;
          var status = data.status || "unknown";
          document.getElementById("progress-text").textContent = status + " — " + done + " / " + total + " regions.";
          if (status !== "done" && status !== "error") setTimeout(poll, 2000);
        })
        .catch(function() { document.getElementById("progress-text").textContent = "Error loading progress."; });
    }
    poll();
  })();
  
})();
