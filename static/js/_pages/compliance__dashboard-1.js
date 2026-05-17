(function(){
  var pageDataEl=document.getElementById("page-data-compliance__dashboard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["compliance__dashboard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
// Mute threat detection
async function muteThreats(duration) {
    const formData = new FormData();
    formData.append('duration', duration);
    
    try {
        const response = await fetch(((window.__RMC_PAGE_DATA__["compliance__dashboard-1"] || {})["url_compliance_api_mute_threats"]), {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': ((window.__RMC_PAGE_DATA__["compliance__dashboard-1"] || {})["var_csrf_token"])
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(result.message);
            window.location.reload();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (error) {
        alert('Failed to update threat mute status: ' + error.message);
    }
}
})();
