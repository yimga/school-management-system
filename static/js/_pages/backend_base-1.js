(function(){
  var pageDataEl=document.getElementById("page-data-backend_base-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["backend_base-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  document.addEventListener('DOMContentLoaded', function () {
    var theme = ((window.__RMC_PAGE_DATA__["backend_base-1"] || {})["var_resolved_backend_console_theme_default_dark"]);
    if (theme === 'system') {
      theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    var darkThemes = ['dark', 'black', 'charcoal', 'graphite', 'midnight', 'ocean', 'steel', 'slate', 'forest', 'indigo', 'amber'];
    var lightThemes = ['light', 'sand', 'snow', 'cream', 'lavender'];
    var resolved = darkThemes.indexOf(theme) >= 0 ? 'dark' : 'light';
    if (darkThemes.indexOf(theme) >= 0) {
      document.body.classList.add('portal-backend-dark');
      document.body.classList.add('portal-backend-' + theme);
    } else {
      document.body.classList.add('portal-backend-light');
      document.body.classList.add('portal-backend-' + theme);
    }
    document.documentElement.setAttribute('data-theme', resolved);
    document.documentElement.setAttribute('data-resolved-theme', resolved);
    document.documentElement.setAttribute('data-bs-theme', resolved);
    document.documentElement.classList.toggle('dark', resolved === 'dark');
  });
})();
