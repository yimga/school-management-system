(function(){
  var pageDataEl=document.getElementById("page-data-reports___report_styles-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["reports___report_styles-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  (function () {
    var token = ((window.__RMC_PAGE_DATA__["reports___report_styles-1"] || {})["var_preview_token_escapejs"]);
    function notifyReady() {
      try {
        if (window.parent && window.parent !== window) {
          window.parent.postMessage(
            {
              type: "reportcard-preview-ready",
              previewToken: token
            },
            window.location.origin
          );
        }
      } catch (error) {
        // Ignore parent messaging failures in print/PDF contexts.
      }
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", notifyReady, { once: true });
      return;
    }
    notifyReady();
  })();
})();
