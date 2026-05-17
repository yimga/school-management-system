(function(){
  var pageDataEl=document.getElementById("page-data-partials__language_switcher-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["partials__language_switcher-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
function setLanguage(languageCode) {
    // Save to localStorage
    localStorage.setItem('preferred_language', languageCode);
    
    // Set cookie for server-side
    document.cookie = `django_language=${languageCode}; path=/; max-age=31536000`;
    
    // Reload page with language parameter
    const url = new URL(window.location);
    url.searchParams.set('language', languageCode);
    window.location.href = url.toString();
}

// Restore preferred language on page load
document.addEventListener('DOMContentLoaded', function() {
    const preferredLanguage = localStorage.getItem('preferred_language');
    if (preferredLanguage && preferredLanguage !== ((window.__RMC_PAGE_DATA__["partials__language_switcher-1"] || {})["var_current_language"])) {
        setLanguage(preferredLanguage);
    }
});
})();
