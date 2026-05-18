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
    // Load recent activity into left sidebar when present (desktop + mobile sidebars)
    (function() {
      var lists = document.querySelectorAll('.recent-activity-list');
      if (!lists.length) return;
      function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = String(text || '');
        return div.innerHTML;
      }
      function setContent(html) {
        for (var i = 0; i < lists.length; i++) lists[i].innerHTML = html;
      }
      function buildItems(data) {
        if (!data || !Array.isArray(data.activities) || data.activities.length === 0) {
          return '<li class="text-muted small px-2">No recent activity.</li>';
        }
        var html = '';
        data.activities.slice(0, 8).forEach(function(item) {
          html += '<li class="sidebar-activity-item px-2 py-1 rounded mb-1" style="border-left:3px solid rgba(99,102,241,0.5);padding-left:0.6rem">' +
            '<span class="fw-semibold d-block" style="font-size:0.8rem">' + escapeHtml(item.title || item.type || 'Event') + '</span>' +
            '<span class="small text-muted">' + escapeHtml(item.description || '') + '</span>' +
            '<span class="badge bg-secondary ms-1" style="font-size:0.65rem">' + escapeHtml(item.when || item.time || '') + '</span></li>';
        });
        return html;
      }
      fetch('/api/activities/?limit=8').then(function(r) { return r.json(); }).then(function(data) {
        setContent(buildItems(data));
      }).catch(function() {
        setContent('<li class="text-muted small px-2">No recent activity.</li>');
      });
    })();
  });
})();
