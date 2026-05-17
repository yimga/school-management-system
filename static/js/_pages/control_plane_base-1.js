(function(){
  var pageDataEl=document.getElementById("page-data-control_plane_base-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["control_plane_base-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function () {
  var offcanvas = document.getElementById('cpSidebarOffcanvas');
  if (!offcanvas) return;
  offcanvas.addEventListener('click', function (e) {
    var link = e.target.closest('a.nav-link');
    if (link && link.getAttribute('href') && link.getAttribute('href') !== '#') {
      var bs = window.bootstrap;
      if (bs && bs.Offcanvas) {
        var instance = bs.Offcanvas.getInstance(offcanvas);
        if (instance) instance.hide();
      }
    }
  });
})();
(function () {
  var nav = document.getElementById('cpSidebarNav');
  var col = document.getElementById('cp-sidebar-col');
  var key = 'runmycampus-cp-sidebar-compact';
  var toggle = document.querySelector('.cp-sidebar-compact-toggle');
  if (!nav || !toggle) return;
  function applyCompact(compact) {
    nav.classList.toggle('cp-sidebar-compact', compact);
    if (col) col.classList.toggle('cp-sidebar-compact', compact);
    try { localStorage.setItem(key, compact ? '1' : '0'); } catch (e) {}
  }
  toggle.addEventListener('click', function () {
    applyCompact(!nav.classList.contains('cp-sidebar-compact'));
  });
  try {
    if (localStorage.getItem(key) === '1') applyCompact(true);
  } catch (e) {}
})();
(function () {
  function getCsrfToken() {
    var name = 'csrftoken=';
    var cookies = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name) === 0) return c.substring(name.length);
    }
    return '';
  }
  var buttons = document.querySelectorAll('.cp-pin-btn[data-cp-pin-id]');
  buttons.forEach(function (btn) {
    if (btn.dataset.cpPinBound === '1') return;
    btn.dataset.cpPinBound = '1';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var id = btn.getAttribute('data-cp-pin-id');
      if (!id) return;
      var isPinned = btn.classList.contains('cp-pin-pinned');
      fetch('/api/control-plane-preferences/', { method: 'GET', credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var list = (data && Array.isArray(data.control_plane_pinned_items)) ? data.control_plane_pinned_items : [];
          if (isPinned) list = list.filter(function (x) { return x !== id; });
          else if (list.indexOf(id) === -1) list.push(id);
          return fetch('/api/control-plane-preferences/', {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken(), 'Accept': 'application/json' },
            body: JSON.stringify({ control_plane_pinned_items: list })
          });
        })
        .then(function (r) { if (!r.ok) throw new Error('Save failed'); return r.json(); })
        .then(function () { window.location.reload(); })
        .catch(function () {});
    });
  });
})();
(function () {
  var gPending = false;
  var gTimeout = null;
  var shortcuts = {
    d: { url: '/super/', label: 'Dashboard' },
    c: { url: '/super/command-center/', label: 'Command Center' },
    t: { url: '/studio/', label: 'Studio OS' },
    o: { url: '/super/orchestration/', label: 'Orchestration' },
    a: { url: '(window.__RMC_PAGE_DATA__["control_plane_base-1"]||{})["url_siteconfig_console_domains_hub"]', label: 'Config center' },
    b: { url: '/super/billing/', label: 'Billing' },
    s: { url: '/super/support/', label: 'Support' },
    m: { url: '/super/migration/', label: 'Migration' },
    u: { url: '/super/usage/', label: 'Usage' },
    h: { url: '/super/tenant-health/', label: 'School Health' },
    p: { url: '/super/pulse/', label: 'Pulse' }
  };
  function showHelp() {
    if (window.RMCShortcuts && typeof window.RMCShortcuts.open === 'function') {
      window.RMCShortcuts.open();
    }
  }
  window.cpShowShortcutsHelp = showHelp;
  document.addEventListener('keydown', function (e) {
    if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      return;
    }
    if (e.key === 'g' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      var tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      e.preventDefault();
      gPending = true;
      clearTimeout(gTimeout);
      gTimeout = setTimeout(function () { gPending = false; }, 1200);
      return;
    }
    if (gPending && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      var info = shortcuts[e.key];
      if (info) {
        e.preventDefault();
        gPending = false;
        clearTimeout(gTimeout);
        window.location.href = info.url;
      }
    }
  });
})();
})();
