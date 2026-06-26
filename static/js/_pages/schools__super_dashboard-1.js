(function(){
  var pageDataEl=document.getElementById("page-data-schools__super_dashboard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["schools__super_dashboard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var pageData = window.__RMC_PAGE_DATA__["schools__super_dashboard-1"] || {};
  var layoutUrl = pageData["var_super_dashboard_layout_url_escapejs"];
  var sectionOrderEl = document.getElementById('cp-section-order-json');
  var sectionOrder = [];
  if (sectionOrderEl) {
    try { sectionOrder = JSON.parse(sectionOrderEl.textContent || '[]'); } catch (_e) {}
  }
  var sectionLabels = pageData.section_labels || {
    'cp-action-queue': 'Action queue',
    'cp-fleet-health': 'Fleet health',
    'cp-global-footprint': 'Global footprint',
    'cp-tenant-registry': 'School registry',
    'cp-readiness': 'Readiness'
  };

  var landingModeRoot = document.querySelector('[data-rmc-cp-landing-mode]');
  if (landingModeRoot) {
    var tabButtons = landingModeRoot.querySelectorAll('[data-rmc-cp-landing-tab]');
    function setLandingMode(mode) {
      landingModeRoot.setAttribute('data-rmc-cp-landing-mode', mode);
      for (var i = 0; i < tabButtons.length; i++) {
        var btn = tabButtons[i];
        var active = btn.getAttribute('data-rmc-cp-landing-tab') === mode;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
      }
      var missionPane = landingModeRoot.querySelector('[data-rmc-cp-landing-pane="mission"]');
      var opsPane = landingModeRoot.querySelector('[data-rmc-cp-landing-pane="operations"]');
      if (missionPane) missionPane.hidden = mode !== 'mission';
      if (opsPane) opsPane.hidden = mode !== 'operations';
      if (mode === 'operations' && opsPane) {
        var main = document.getElementById('super-dashboard-main');
        if (main && typeof main.focus === 'function') {
          try { main.focus({ preventScroll: false }); } catch (_f) { main.focus(); }
        }
      }
    }
    for (var t = 0; t < tabButtons.length; t++) {
      tabButtons[t].addEventListener('click', function(ev) {
        var mode = ev.currentTarget.getAttribute('data-rmc-cp-landing-tab');
        if (mode) setLandingMode(mode);
      });
    }
    setLandingMode(landingModeRoot.getAttribute('data-rmc-cp-landing-mode') || 'mission');
  }

  var modal = document.getElementById('cp-layout-modal');
  var listEl = document.getElementById('cp-layout-sortable');
  var saveBtn = document.getElementById('cp-layout-save');
  var customizeBtn = document.getElementById('cp-customize-layout-btn');
  if (!modal || !listEl || !saveBtn || !customizeBtn || !layoutUrl) return;

  function renderList(order) {
    listEl.innerHTML = order.map(function(id) {
      return '<li class="list-group-item d-flex align-items-center gap-2" data-section-id="' + id + '"><span class="text-muted small">⋮⋮</span> ' + (sectionLabels[id] || id) + '</li>';
    }).join('');
  }
  function getOrder() {
    return [].map.call(listEl.querySelectorAll('[data-section-id]'), function(el) { return el.getAttribute('data-section-id'); });
  }

  var sortableInstance = null;
  function initSortable() {
    if (sortableInstance) return;
    if (window.Sortable) {
      sortableInstance = new Sortable(listEl, { animation: 150, handle: '.text-muted' });
      return;
    }
    var s = document.createElement('script');
    s.src = pageData.sortable_js_url || '/static/js/sortable.min.js';
    s.onload = function() { sortableInstance = new Sortable(listEl, { animation: 150, handle: '.text-muted' }); };
    document.head.appendChild(s);
  }

  customizeBtn.addEventListener('click', function() {
    renderList(sectionOrder);
    if (window.bootstrap && window.bootstrap.Modal) {
      var m = new window.bootstrap.Modal(modal);
      m.show();
    } else { modal.style.display = 'block'; }
    setTimeout(initSortable, 100);
  });

  saveBtn.addEventListener('click', function() {
    var order = getOrder();
    saveBtn.disabled = true;
    var csrf = (document.querySelector('[name=csrfmiddlewaretoken]') && document.querySelector('[name=csrfmiddlewaretoken]')?.value) || (function() { var m = document.cookie.match(/csrftoken=([^;]+)/); return m ? m[1] : ''; })();
    fetch(layoutUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ section_order: order })
    }).then(function(r) { return r.json(); })
      .then(function(data) {
        sectionOrder = data.section_order || order;
        if (window.bootstrap && modal._modal) modal._modal.hide(); else modal.style.display = 'none';
      })
      .catch(function() {})
      .finally(function() { saveBtn.disabled = false; });
  });
})();
})();
