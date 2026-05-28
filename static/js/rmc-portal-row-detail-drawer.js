/**
 * Portal row detail drawer — gradebook, attendance, operator data tables.
 * Explicit rows: data-rmc-row-detail="1" + title/subtitle/meta attrs.
 * Auto rows: table data-rmc-row-detail-auto="1" scrapes thead/tbody cells.
 */
(function () {
  'use strict';

  function cellText(cell) {
    if (!cell) return '';
    return (cell.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function parseJsonAttr(row, attr, fallback) {
    var raw = row.getAttribute(attr);
    if (!raw) { return fallback; }
    try {
      return JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function resolveRowPayload(row, table) {
    if (row.getAttribute('data-rmc-row-detail') === '1') {
      var meta = parseJsonAttr(row, 'data-rmc-row-meta', {});
      var actions = parseJsonAttr(row, 'data-rmc-row-actions', []);
      if (!Array.isArray(actions)) { actions = []; }
      return {
        title: row.getAttribute('data-rmc-row-title') || 'Row',
        subtitle: row.getAttribute('data-rmc-row-subtitle') || '',
        meta: meta,
        actions: actions,
      };
    }
    if (!table || table.getAttribute('data-rmc-row-detail-auto') !== '1') {
      return null;
    }
    var cells = row.querySelectorAll('td, th');
    if (!cells.length) return null;
    var headers = table.querySelectorAll('thead th');
    var title = cellText(cells[0]) || 'Row';
    var subtitle = cells.length > 1 ? cellText(cells[1]) : '';
    var meta = {};
    var start = 2;
    for (var i = start; i < cells.length; i += 1) {
      var key = cellText(headers[i]) || ('Column ' + (i + 1));
      if (!key) continue;
      meta[key] = cellText(cells[i]) || '—';
    }
    return { title: title, subtitle: subtitle, meta: meta };
  }

  function renderActions(actions) {
    var wrap = document.getElementById('rmcPortalRowDetailActions');
    if (!wrap) return;
    wrap.innerHTML = '';
    if (!actions || !actions.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    actions.forEach(function (act) {
      if (!act || !act.href) return;
      var a = document.createElement('a');
      a.className = 'btn btn-sm ' + (act.variant === 'primary' ? 'btn-primary' : 'btn-outline-primary');
      a.href = act.href;
      a.textContent = act.label || 'Open';
      if (act.target) a.setAttribute('target', act.target);
      if (act.rel) a.setAttribute('rel', act.rel);
      wrap.appendChild(a);
    });
  }

  function emitRowContext(payload) {
    try {
      document.dispatchEvent(
        new CustomEvent('rmc:row-detail-open', { detail: payload, bubbles: true })
      );
    } catch (_e) {}
  }

  function openDrawer(row, table) {
    var payload = resolveRowPayload(row, table);
    if (!payload) return;
    var drawerEl = document.getElementById('rmcPortalRowDetailDrawer');
    if (!drawerEl || !window.bootstrap || !window.bootstrap.Offcanvas) return;
    var titleEl = document.getElementById('rmcPortalRowDetailDrawerLabel');
    var subEl = document.getElementById('rmcPortalRowDetailSubtitle');
    var bodyEl = document.getElementById('rmcPortalRowDetailBody');
    if (titleEl) titleEl.textContent = payload.title;
    if (subEl) subEl.textContent = payload.subtitle;
    if (bodyEl) {
      bodyEl.innerHTML = '';
      Object.keys(payload.meta).forEach(function (key) {
        var dt = document.createElement('dt');
        dt.textContent = key;
        var dd = document.createElement('dd');
        dd.textContent = String(payload.meta[key] == null ? '—' : payload.meta[key]);
        bodyEl.appendChild(dt);
        bodyEl.appendChild(dd);
      });
    }
    renderActions(payload.actions);
    emitRowContext(payload);
    window.bootstrap.Offcanvas.getOrCreateInstance(drawerEl).show();
  }

  function isInteractiveTarget(target) {
    return !!(target && target.closest('input, select, textarea, button, a, label, form'));
  }

  function prepareAutoRows(table) {
    if (!table || table.getAttribute('data-rmc-row-detail-auto') !== '1') return;
    table.querySelectorAll('tbody tr').forEach(function (row) {
      if (row.getAttribute('data-rmc-row-detail') === '1') return;
      row.setAttribute('data-rmc-row-detail', '1');
      if (!row.hasAttribute('tabindex')) row.setAttribute('tabindex', '0');
    });
  }

  function bindTable(table) {
    if (!table || table.getAttribute('data-rmc-row-detail-bound') === '1') return;
    table.setAttribute('data-rmc-row-detail-bound', '1');
    prepareAutoRows(table);
    table.addEventListener('click', function (ev) {
      if (isInteractiveTarget(ev.target)) return;
      var row = ev.target && ev.target.closest('tbody tr');
      if (!row) return;
      openDrawer(row, table);
    });
    table.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var row = ev.target && ev.target.closest('tbody tr');
      if (!row) return;
      if (isInteractiveTarget(ev.target)) return;
      ev.preventDefault();
      openDrawer(row, table);
    });
  }

  function bindCardSurface(surface) {
    if (!surface || surface.getAttribute('data-rmc-row-detail-cards-bound') === '1') return;
    surface.setAttribute('data-rmc-row-detail-cards-bound', '1');
    surface.querySelectorAll('[data-rmc-row-detail="1"]').forEach(function (card) {
      card.addEventListener('click', function (ev) {
        if (isInteractiveTarget(ev.target)) return;
        openDrawer(card, null);
      });
      card.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        if (isInteractiveTarget(ev.target)) return;
        ev.preventDefault();
        openDrawer(card, null);
      });
    });
  }

  function init() {
    document.querySelectorAll('[data-rmc-row-detail-table="1"]').forEach(bindTable);
    document.querySelectorAll('[data-rmc-row-detail-cards="1"]').forEach(bindCardSurface);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

