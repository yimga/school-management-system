(function(){
  var pageDataEl=document.getElementById("page-data-components__pin_to_quick_access-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["components__pin_to_quick_access-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var btn = document.querySelector('.page-pin-btn[data-sidebar-id="(window.__RMC_PAGE_DATA__["components__pin_to_quick_access-1"]||{})["var_sidebar_item_id"]"]');
  if (!btn) return;
  function getCsrfToken() {
    var name = 'csrftoken';
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name + '=') === 0) return c.substring(name.length + 1);
    }
    return '';
  }
  btn.addEventListener('click', function(e) {
    e.preventDefault();
    var id = this.getAttribute('data-sidebar-id');
    var isPinned = this.getAttribute('data-pinned') === 'true';
    if (!id) return;
    btn.disabled = true;
    fetch('/api/portal-preferences/', { method: 'GET', credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var list = data.pinned_sidebar_items || [];
        if (isPinned) list = list.filter(function(x) { return x !== id; });
        else if (list.indexOf(id) === -1) list.push(id);
        return fetch('/api/portal-preferences/', {
          method: 'PATCH',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken(), 'Accept': 'application/json' },
          body: JSON.stringify({ pinned_sidebar_items: list })
        });
      })
      .then(function(r) { if (r.ok) return r.json(); throw new Error(); })
      .then(function() { window.location.reload(); })
      .catch(function() { btn.disabled = false; });
  });
})();
})();
