/**
 * Portal row detail drawer — teacher gradebook + attendance tables.
 */
(function () {
  'use strict';

  function openDrawer(row) {
    var drawerEl = document.getElementById('rmcPortalRowDetailDrawer');
    if (!drawerEl || !window.bootstrap || !window.bootstrap.Offcanvas) return;
    var title = row.getAttribute('data-rmc-row-title') || 'Student';
    var subtitle = row.getAttribute('data-rmc-row-subtitle') || '';
    var metaRaw = row.getAttribute('data-rmc-row-meta') || '{}';
    var meta = {};
    try {
      meta = JSON.parse(metaRaw);
    } catch (e) {
      meta = {};
    }
    var titleEl = document.getElementById('rmcPortalRowDetailDrawerLabel');
    var subEl = document.getElementById('rmcPortalRowDetailSubtitle');
    var bodyEl = document.getElementById('rmcPortalRowDetailBody');
    if (titleEl) titleEl.textContent = title;
    if (subEl) subEl.textContent = subtitle;
    if (bodyEl) {
      bodyEl.innerHTML = '';
      Object.keys(meta).forEach(function (key) {
        var dt = document.createElement('dt');
        dt.textContent = key;
        var dd = document.createElement('dd');
        dd.textContent = String(meta[key] == null ? '—' : meta[key]);
        bodyEl.appendChild(dt);
        bodyEl.appendChild(dd);
      });
    }
    window.bootstrap.Offcanvas.getOrCreateInstance(drawerEl).show();
  }

  function bindTable(table) {
    if (!table || table.getAttribute('data-rmc-row-detail-bound') === '1') return;
    table.setAttribute('data-rmc-row-detail-bound', '1');
    table.addEventListener('click', function (ev) {
      var target = ev.target;
      if (target && (target.closest('input, select, textarea, button, a, label'))) return;
      var row = target && target.closest('tr[data-rmc-row-detail="1"]');
      if (row) openDrawer(row);
    });
    table.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var row = ev.target && ev.target.closest('tr[data-rmc-row-detail="1"]');
      if (!row) return;
      ev.preventDefault();
      openDrawer(row);
    });
  }

  function init() {
    document.querySelectorAll('[data-rmc-row-detail-table="1"]').forEach(bindTable);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
