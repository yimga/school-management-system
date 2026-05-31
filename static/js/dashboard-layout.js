(function () {
  const ready = (fn) => (document.readyState !== 'loading' ? fn() : document.addEventListener('DOMContentLoaded', fn));

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  function layoutUrl(page) {
    const ps = window.RMCPlatformSurface;
    if (!ps || typeof ps.templated !== 'function') return '';
    return ps.templated('dashboard_layout', { page: page || '' });
  }

  function availableWidgetsUrl(page) {
    const base = window.RMCPlatformSurface && window.RMCPlatformSurface.url('dashboard_available_widgets');
    if (!base) return '';
    const sep = base.indexOf('?') >= 0 ? '&' : '?';
    return base + sep + 'page=' + encodeURIComponent(page || '');
  }

  async function loadSortable() {
    if (window.Sortable) return window.Sortable;
    const localSrc = '/static/js/sortable.min.js';
    const cdnSrc = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js';
    return new Promise((resolve) => {
      function tryLoad(url) {
        const s = document.createElement('script');
        s.src = url;
        s.async = true;
        s.onload = () => resolve(window.Sortable);
        s.onerror = () => (url === cdnSrc ? resolve(null) : tryLoad(cdnSrc));
        document.head.appendChild(s);
      }
      tryLoad(localSrc);
    });
  }

  function ensureColumnKeys(columns) {
    // Many pages have multiple containers with the same data-dashboard-column value.
    // To keep persistence stable, we assign each container a unique key (stable as
    // long as the page template doesn't change its container count/order).
    columns.forEach((col, idx) => {
      if (!col.dataset.dashboardColumnKey) {
        const base = col.dataset.dashboardColumn || 'main';
        col.dataset.dashboardColumnKey = `${base}#${idx}`;
      }
    });
  }

  function collectLayout(columns) {
    const items = [];
    columns.forEach((col) => {
      const columnKey = col.dataset.dashboardColumnKey || col.dataset.dashboardColumn || 'main';
      Array.from(col.querySelectorAll('[data-widget-id]')).forEach((el, idx) => {
        const it = {
          id: el.dataset.widgetId,
          column: columnKey,
          order: idx,
          size: el.dataset.widgetSize || null,
          variant: el.dataset.widgetVariant || null,
        };
        if (el.dataset.widgetChartType) it.chart_type = el.dataset.widgetChartType;
        items.push(it);
      });
    });
    return { items };
  }

  function collectWidgetMeta(columns) {
    const meta = {};
    columns.forEach((col) => {
      Array.from(col.querySelectorAll('[data-widget-id]')).forEach((el) => {
        const id = el.dataset.widgetId;
        if (!id) return;
        meta[id] = {
          size: el.dataset.widgetSize || 'md',
          variant: el.dataset.widgetVariant || 'default',
        };
        if (el.dataset.widgetChartType) meta[id].chart_type = el.dataset.widgetChartType;
      });
    });
    return meta;
  }

  function applyLayout(columns, layout) {
    if (!layout || !layout.items) return;
    const byId = {};
    columns.forEach((col) => {
      col.querySelectorAll('[data-widget-id]').forEach((el) => {
        byId[el.dataset.widgetId] = el;
      });
    });
    layout.items
      .sort((a, b) => (a.order || 0) - (b.order || 0))
      .forEach((item) => {
        const targetCol =
          document.querySelector(`[data-dashboard-column-key="${item.column}"]`) ||
          document.querySelector(`[data-dashboard-column="${item.column}"]`);
        const el = byId[item.id];
        if (targetCol && el) targetCol.appendChild(el);
      });
  }

  function normalizeSize(size) {
    const v = (size || '').toString().trim().toLowerCase();
    if (!v) return null;
    if (v === 'small') return 'sm';
    if (v === 'medium') return 'md';
    if (v === 'large') return 'lg';
    return v;
  }

  function normalizeVariant(variant) {
    const v = (variant || '').toString().trim().toLowerCase();
    return v || null;
  }

  function applyPresentation(el, item, meta) {
    const allowedSizes = (meta && meta.allowed_sizes) || ['sm', 'md', 'lg'];
    const allowedVariants = (meta && meta.allowed_variants) || ['default', 'compact', 'flat'];

    const size = normalizeSize(item && item.size) || normalizeSize(el.dataset.widgetSize) || normalizeSize(meta && meta.default_size) || 'md';
    const variant =
      normalizeVariant(item && item.variant) || normalizeVariant(el.dataset.widgetVariant) || normalizeVariant(meta && meta.default_variant) || 'default';

    el.dataset.widgetSize = allowedSizes.includes(size) ? size : (allowedSizes[0] || 'md');
    el.dataset.widgetVariant = allowedVariants.includes(variant) ? variant : (allowedVariants[0] || 'default');

    if ((meta && meta.widget_type) === 'chart' && (meta.chart_type || item.chart_type)) {
      const ct = (meta.chart_type || item.chart_type || '').toLowerCase();
      if (['line','bar','pie','doughnut','radar','polararea'].includes(ct)) {
        el.dataset.widgetChartType = ct === 'polararea' ? 'polarArea' : ct;
      }
    }
  }

  function injectGrip(el, onMoveUpDown) {
    if (el.querySelector('.dashboard-widget-grip')) return;
    const grip = document.createElement('div');
    grip.className = 'dashboard-widget-grip';
    grip.setAttribute('aria-label', 'Drag to reorder');
    grip.setAttribute('title', 'Drag to reorder. Arrow keys or buttons: move up/down.');
    grip.setAttribute('tabindex', '0');
    grip.setAttribute('role', 'button');
    grip.innerHTML = '<span class="dashboard-widget-grip-dots" aria-hidden="true">&#x22EE;&#x22EE;</span>';
    if (typeof onMoveUpDown === 'function') {
      grip.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowUp') { e.preventDefault(); onMoveUpDown(el, -1); }
        if (e.key === 'ArrowDown') { e.preventDefault(); onMoveUpDown(el, 1); }
      });
      var upBtn = document.createElement('button');
      upBtn.type = 'button';
      upBtn.className = 'dash-widget-move-btn d-block d-md-none';
      upBtn.setAttribute('aria-label', 'Move up');
      upBtn.innerHTML = '<i class="bi bi-chevron-up"></i>';
      upBtn.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); onMoveUpDown(el, -1); });
      var downBtn = document.createElement('button');
      downBtn.type = 'button';
      downBtn.className = 'dash-widget-move-btn d-block d-md-none';
      downBtn.setAttribute('aria-label', 'Move down');
      downBtn.innerHTML = '<i class="bi bi-chevron-down"></i>';
      downBtn.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); onMoveUpDown(el, 1); });
      grip.appendChild(upBtn);
      grip.appendChild(downBtn);
    }
    el.insertBefore(grip, el.firstChild);
  }

  const CHART_TYPES = [
    { value: 'line', label: 'Line' },
    { value: 'bar', label: 'Bar' },
    { value: 'pie', label: 'Pie' },
    { value: 'doughnut', label: 'Doughnut' },
    { value: 'radar', label: 'Radar' },
    { value: 'polarArea', label: 'Polar Area' },
  ];

  function injectControls(el, meta, onChange, isLightMode, noHideWidgetIds) {
    if (el.dataset.widgetControlsInjected === '1') return;
    el.dataset.widgetControlsInjected = '1';

    const allowedSizes = (meta && meta.allowed_sizes) || ['sm', 'md', 'lg'];
    const allowedVariants = (meta && meta.allowed_variants) || ['default', 'compact', 'flat'];
    const isChartWidget = (meta && meta.widget_type) === 'chart';
    const wid = el.dataset.widgetId || '';
    const canHide = !Array.isArray(noHideWidgetIds) || noHideWidgetIds.indexOf(wid) < 0;

    el.classList.add('dash-widget');
    if (!isLightMode) injectGrip(el);

    let menuRows = '';
    if (!isLightMode) {
      menuRows = `
      <div class="dash-widget-row">
        <label>Size</label>
        <select class="dash-widget-size"></select>
      </div>
      <div class="dash-widget-row">
        <label>Style</label>
        <select class="dash-widget-variant"></select>
      </div>
    `;
    }
    if (!isLightMode && isChartWidget) {
      menuRows += `
      <div class="dash-widget-row">
        <label>Chart</label>
        <select class="dash-widget-chart-type"></select>
      </div>
      `;
    }
    if (canHide) {
      menuRows += `
      <div class="dash-widget-row">
        <button type="button" class="dash-widget-hide-btn btn btn-sm btn-outline-secondary w-100">Hide widget</button>
      </div>
    `;
    }

    const isBackend = document.body && document.body.dataset.dashboardPage === 'backend';
    const gearLabel = isBackend ? '' : '<span class="dash-widget-gear-label d-none d-md-inline ms-1">Settings</span>';
    const controls = document.createElement('div');
    controls.className = 'dash-widget-controls';
    controls.innerHTML = `
      <button type="button" class="dash-widget-gear" aria-label="Widget settings" title="Widget settings"><span class="dash-widget-gear-dots" aria-hidden="true">&#x22EF;</span>${gearLabel}</button>
      <div class="dash-widget-menu" aria-hidden="true">${menuRows}</div>
    `;

    const sizeSelect = controls.querySelector('.dash-widget-size');
    const variantSelect = controls.querySelector('.dash-widget-variant');
    const chartTypeSelect = controls.querySelector('.dash-widget-chart-type');
    const gear = controls.querySelector('.dash-widget-gear');
    const menu = controls.querySelector('.dash-widget-menu');

    allowedSizes.forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s;
      opt.textContent = s === 'sm' ? 'Small' : s === 'lg' ? 'Large' : 'Medium';
      sizeSelect.appendChild(opt);
    });
    allowedVariants.forEach((v) => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v === 'flat' ? 'Flat' : v === 'compact' ? 'Compact' : 'Default';
      variantSelect.appendChild(opt);
    });
    if (isChartWidget && chartTypeSelect) {
      CHART_TYPES.forEach((ct) => {
        const opt = document.createElement('option');
        opt.value = ct.value;
        opt.textContent = ct.label;
        chartTypeSelect.appendChild(opt);
      });
    }

    if (sizeSelect) sizeSelect.value = normalizeSize(el.dataset.widgetSize) || 'md';
    if (variantSelect) variantSelect.value = normalizeVariant(el.dataset.widgetVariant) || 'default';
    if (isChartWidget && chartTypeSelect) {
      const ct = (el.dataset.widgetChartType || meta.chart_type || '').toLowerCase();
      chartTypeSelect.value = CHART_TYPES.some((c) => c.value === ct) ? ct : (meta.chart_type || 'line');
    }

    const closeMenu = () => {
      menu.setAttribute('aria-hidden', 'true');
      controls.classList.remove('is-open');
    };

    gear.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const open = menu.getAttribute('aria-hidden') !== 'true';
      if (open) closeMenu();
      else {
        menu.setAttribute('aria-hidden', 'false');
        controls.classList.add('is-open');
      }
    });

    document.addEventListener('click', (evt) => {
      if (!controls.contains(evt.target)) closeMenu();
    });

    if (sizeSelect) {
      sizeSelect.addEventListener('change', () => {
        el.dataset.widgetSize = sizeSelect.value;
        onChange();
      });
    }
    if (variantSelect) {
      variantSelect.addEventListener('change', () => {
        el.dataset.widgetVariant = variantSelect.value;
        onChange();
      });
    }
    if (isChartWidget && chartTypeSelect) {
      chartTypeSelect.addEventListener('change', () => {
        el.dataset.widgetChartType = chartTypeSelect.value;
        if (window.dashboardCharts && typeof window.dashboardCharts.refreshCharts === 'function') {
          window.dashboardCharts.refreshCharts();
        }
        onChange();
      });
    }
    const pinBtn = isLightMode ? null : controls.querySelector('.dash-widget-pin-btn');
    if (pinBtn) {
      pinBtn.addEventListener('click', function () {
        const wid = el.dataset.widgetId;
        if (!wid) return;
        const pages = ['backend', 'teacher', 'parent'].filter((p) => p !== page);
        if (pages.length === 0) return;
        const existing = pinnedWidgets.find((x) => x.widget_id === wid);
        const targetPage = pages[0];
        if (existing) {
          if (!existing.pages.includes(targetPage)) {
            existing.pages.push(targetPage);
          } else {
            existing.pages = existing.pages.filter((p) => p !== targetPage);
            if (existing.pages.length === 0) {
              pinnedWidgets = pinnedWidgets.filter((x) => x.widget_id !== wid);
            }
          }
        } else {
          pinnedWidgets.push({ widget_id: wid, pages: [targetPage] });
        }
        if (typeof onChange === 'function') onChange();
        closeMenu();
        showToast('Widget pinned. Cross-page display coming soon.');
      });
    }

    const hideBtn = controls.querySelector('.dash-widget-hide-btn');
    if (hideBtn) {
      const isHidden = el.classList.contains('dash-widget-hidden') || el.style.display === 'none';
      hideBtn.textContent = isHidden ? 'Show widget' : 'Hide widget';
      hideBtn.addEventListener('click', () => {
        const wid = el.dataset.widgetId;
        if (!wid) return;
        const idx = hiddenWidgetIds.indexOf(wid);
        if (idx >= 0) {
          hiddenWidgetIds.splice(idx, 1);
          el.classList.remove('dash-widget-hidden');
          el.style.display = '';
          hideBtn.textContent = 'Hide widget';
        } else {
          hiddenWidgetIds.push(wid);
          el.classList.add('dash-widget-hidden');
          el.style.display = 'none';
          hideBtn.textContent = 'Show widget';
        }
        if (typeof onChange === 'function') onChange();
      });
    }

    el.appendChild(controls);
  }

  function initDragDrop(page) {
    const layoutRoot = document.getElementById('dashboard-layout');
    if (!layoutRoot) return;
    
    // Find explicit column containers, or fall back to treating the root as a single column
    let columns = Array.from(layoutRoot.querySelectorAll('[data-dashboard-column]'));
    if (!columns.length) {
      // No explicit columns: treat the root container as a single column
      if (!layoutRoot.dataset.dashboardColumn) {
        layoutRoot.dataset.dashboardColumn = 'main';
      }
      columns = [layoutRoot];
    }
    
    if (!page) {
      // Try to infer page from body dataset or URL
      page = (document.body.dataset.dashboardPage || '').toLowerCase();
      if (!page) {
        const path = window.location.pathname;
        if (path.includes('/parent/')) page = 'parent';
        else if (path.includes('/teacher/')) page = 'teacher';
        else if (path.includes('/backend/')) page = 'backend';
        else if (path.includes('/finance/')) page = 'finance';
        else if (path.includes('/analytics/')) page = 'analytics';
        else if (path.includes('/payroll/')) page = 'payroll';
        else if (path.includes('/emis/')) page = 'emis';
        else page = 'backend'; // default
      }
    }
    
    if (!page) return;

    // Backend: these widgets must always be visible (keep in sync with API BACKEND_ALWAYS_VISIBLE_WIDGET_IDS)
    var BACKEND_ALWAYS_VISIBLE = ['backend-recent-activity', 'backend-top-performing', 'backend-attendance-today'];

    ensureColumnKeys(columns);

    let widgetMetaById = {};
    const dragToggle = document.getElementById('toggleLayoutDrag') || document.getElementById('toggleCustomize');
    let sortables = [];

    function showToast(message, tone, withRetry, undoFn) {
      const container = document.getElementById('dashboard-layout-toast');
      if (!container) return;
      const toast = document.createElement('div');
      toast.className = 'dashboard-layout-toast-item alert shadow-sm mb-0 d-flex align-items-center justify-content-between gap-2';
      toast.classList.add(tone === 'error' ? 'alert-danger' : tone === 'warning' ? 'alert-warning' : 'alert-success');
      toast.setAttribute('role', 'status');
      const span = document.createElement('span');
      span.textContent = message;
      toast.appendChild(span);
      if (withRetry) {
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-outline-dark';
        btn.textContent = 'Retry';
        btn.addEventListener('click', () => { toast.remove(); saveLayout(); });
        toast.appendChild(btn);
      } else if (typeof undoFn === 'function') {
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-outline-dark';
        btn.textContent = 'Undo';
        btn.setAttribute('aria-label', 'Undo last layout change');
        btn.addEventListener('click', () => { toast.remove(); undoFn(); });
        toast.appendChild(btn);
      }
      container.appendChild(toast);
      setTimeout(() => toast.remove(), withRetry ? 8000 : (undoFn ? 5500 : 2500));
    }

    function moveWidgetInColumn(col, el, delta, doSave) {
      const widgets = Array.from(col.querySelectorAll('[data-widget-id]'));
      const idx = widgets.indexOf(el);
      if (idx < 0) return;
      const newIdx = Math.max(0, Math.min(widgets.length - 1, idx + delta));
      if (newIdx === idx) return;
      preDragSnapshot = snapshotDom();
      if (delta < 0) col.insertBefore(el, widgets[newIdx]);
      else col.insertBefore(el, widgets[newIdx].nextSibling);
      if (doSave) saveLayout({ undoable: true });
    }

    let hiddenWidgetIds = [];
    let pinnedWidgets = [];
    let preDragSnapshot = null;

    const snapshotDom = () => {
      const snap = [];
      columns.forEach((col) => {
        const key = col.dataset.dashboardColumnKey || col.dataset.dashboardColumn || 'main';
        const ids = Array.from(col.querySelectorAll('[data-widget-id]')).map((el) => el.dataset.widgetId);
        snap.push({ column: key, ids: ids });
      });
      return snap;
    };

    const restoreSnapshot = (snap) => {
      if (!snap) return;
      const byId = {};
      columns.forEach((col) => {
        col.querySelectorAll('[data-widget-id]').forEach((el) => { byId[el.dataset.widgetId] = el; });
      });
      snap.forEach((colSnap) => {
        const targetCol = document.querySelector(`[data-dashboard-column-key="${colSnap.column}"]`)
          || document.querySelector(`[data-dashboard-column="${colSnap.column}"]`);
        if (!targetCol) return;
        colSnap.ids.forEach((id) => {
          const el = byId[id];
          if (el) targetCol.appendChild(el);
        });
      });
    };

    const saveLayout = (opts) => {
      const offerUndo = !!(opts && opts.undoable && preDragSnapshot);
      const undoTarget = offerUndo ? preDragSnapshot.slice() : null;
      const itemsPayload = collectLayout(columns);
      const widgetMeta = collectWidgetMeta(columns);
      fetch(layoutUrl(page), { credentials: 'include' })
        .then((r) => (r.ok ? r.json() : null))
        .then((current) => {
          const layout = (current && current.layout) || {};
          const settings = Object.assign({}, layout.__settings__ || {});
          settings.widget_meta = Object.assign({}, settings.widget_meta || {}, widgetMeta);
          settings.hidden_widget_ids = hiddenWidgetIds;
          settings.pinned_widgets = pinnedWidgets;
          const payload = {
            items: itemsPayload.items,
            __settings__: settings,
          };
          return fetch(layoutUrl(page), {
            method: 'PUT',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ layout: payload }),
          });
        })
        .then((r) => {
          if (r && r.ok) {
            if (offerUndo) {
              showToast('Layout saved', null, false, () => {
                restoreSnapshot(undoTarget);
                preDragSnapshot = null;
                saveLayout();
              });
            } else {
              showToast('Layout saved');
            }
          } else {
            showToast('Could not save layout.', 'error', true);
          }
        })
        .catch(() => showToast('Could not save layout.', 'error', true));
    };

    const resetLayout = () => {
      fetch(layoutUrl(page), {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'X-CSRFToken': getCsrfToken() },
      })
        .then((r) => {
          if (r && r.ok) return fetch(layoutUrl(page), { credentials: 'include' });
          throw new Error('Reset failed');
        })
        .then((r) => (r && r.ok ? r.json() : null))
        .then((data) => {
          if (data && data.layout) applyLayout(columns, data.layout);
          showToast('Layout reset to default');
          window.location.reload();
        })
        .catch(() => showToast('Could not reset layout'));
    };

    document.querySelectorAll('.js-reset-dashboard-layout').forEach((btn) => {
      btn.addEventListener('click', () => resetLayout());
    });

    function openAddWidgetPalette() {
      const listEl = document.getElementById('addWidgetList');
      const modalEl = document.getElementById('addWidgetModal');
      if (!listEl || !modalEl) return;
      listEl.innerHTML = '<div class="text-muted small"><span class="spinner-border spinner-border-sm me-2"></span>Loading...</div>';
      if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
      } else {
        modalEl.classList.add('show');
        modalEl.style.display = 'block';
      }
      function closeModal() {
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
          const modal = bootstrap.Modal.getInstance(modalEl);
          if (modal) modal.hide();
        } else {
          modalEl.classList.remove('show');
          modalEl.style.display = 'none';
        }
      }
      function formatLabel(id) {
        return (id || '').replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      }
      function escapeHtml(s) { return (s || '').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
      function widgetRowHtml(name, desc, dataAttr, dataValue, actionLabel, badge) {
        return `
          <div class="list-group-item d-flex justify-content-between align-items-center px-0">
            <div class="me-2">
              <strong>${escapeHtml(name)}</strong>
              ${badge ? `<span class="badge bg-light text-dark ms-2">${escapeHtml(badge)}</span>` : ''}
              ${desc ? `<div class="small text-muted">${escapeHtml(desc).substring(0, 120)}</div>` : ''}
            </div>
            <button type="button" class="btn btn-sm btn-primary gallery-add-btn" ${dataAttr}="${(dataValue || '').replace(/"/g, '&quot;')}">
              ${escapeHtml(actionLabel)}
            </button>
          </div>
        `;
      }
      fetch(availableWidgetsUrl(page), { credentials: 'include' })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          const widgets = (data && data.widgets) || [];
          const cockpitWidgets = (data && data.cockpit_widgets) || [];
          const marketplaceWidgets = (data && data.marketplace_widgets) || [];
          const widgetById = {};
          widgets.forEach((w) => { if (w.id) widgetById[w.id] = w; });
          // Discover all widget IDs already in the DOM (visible OR hidden)
          const placedIds = new Set();
          columns.forEach((col) => {
            col.querySelectorAll('[data-widget-id]').forEach((el) => {
              const wid = el.dataset.widgetId;
              if (wid) placedIds.add(wid);
            });
          });
          const hidden = hiddenWidgetIds.filter((id) => id);
          // Discoverable = catalog widgets that are NOT currently in the DOM at all.
          const discoverable = widgets.filter((w) => w.id && !placedIds.has(w.id));

          let html = '';
          // Section 1: Hidden widgets (restorable)
          if (hidden.length > 0) {
            html += '<h6 class="text-muted text-uppercase small fw-semibold mt-1 mb-2">Hidden — restore</h6><div class="list-group list-group-flush mb-3">';
            hidden.forEach((wid) => {
              const w = widgetById[wid];
              const name = (w && w.name) || formatLabel(wid);
              const desc = (w && w.description) || '';
              html += widgetRowHtml(name, desc, 'data-restore-widget-id', wid, 'Restore');
            });
            html += '</div>';
          }
          // Section 2: Discoverable (never placed) built-in widgets
          if (discoverable.length > 0) {
            html += '<h6 class="text-muted text-uppercase small fw-semibold mt-1 mb-2">Available — add new</h6><div class="list-group list-group-flush mb-3">';
            discoverable.forEach((w) => {
              html += widgetRowHtml(w.name || formatLabel(w.id), w.description || '', 'data-add-widget-id', w.id, 'Add to dashboard');
            });
            html += '</div>';
          }
          // Section 3: Cockpit-section catalog — promote-to-dashboard action live as of v3.99.24
          if (cockpitWidgets.length > 0) {
            html += '<h6 class="text-muted text-uppercase small fw-semibold mt-1 mb-2">Cockpit sections — promote to dashboard</h6><div class="list-group list-group-flush mb-1">';
            cockpitWidgets.forEach((cw) => {
              const badge = cw.cockpit_host_scope || '';
              const placed = placedIds.has(cw.id);
              const label = placed ? 'Already on dashboard' : 'Promote';
              html += `
                <div class="list-group-item d-flex justify-content-between align-items-center px-0">
                  <div class="me-2">
                    <strong>${escapeHtml(cw.name || cw.id)}</strong>
                    ${badge ? `<span class="badge bg-light text-dark ms-2">${escapeHtml(badge)}</span>` : ''}
                    ${cw.description ? `<div class="small text-muted">${escapeHtml(cw.description).substring(0, 120)}</div>` : ''}
                  </div>
                  <div class="d-flex gap-2">
                    <button type="button" class="btn btn-sm btn-outline-secondary" data-cockpit-configure-id="${(cw.id || '').replace(/"/g, '&quot;')}" title="Open cockpit configure page for this section">
                      <i class="bi bi-gear" aria-hidden="true"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-primary" data-cockpit-promote-id="${(cw.id || '').replace(/"/g, '&quot;')}" ${placed ? 'disabled' : ''}>
                      ${escapeHtml(label)}
                    </button>
                  </div>
                </div>
              `;
            });
            html += '</div>';
          }
          // Section 4: Marketplace-installed widgets (v4.00.5)
          if (marketplaceWidgets.length > 0) {
            html += '<h6 class="text-muted text-uppercase small fw-semibold mt-1 mb-2">Marketplace apps</h6><div class="list-group list-group-flush mb-1">';
            marketplaceWidgets.forEach((mw) => {
              const badge = mw.app_slug || 'app';
              html += `
                <div class="list-group-item d-flex justify-content-between align-items-center px-0">
                  <div class="me-2">
                    <strong>${escapeHtml(mw.name || mw.id)}</strong>
                    <span class="badge bg-light text-dark ms-2">${escapeHtml(badge)}</span>
                    ${mw.description ? `<div class="small text-muted">${escapeHtml(mw.description).substring(0, 120)}</div>` : ''}
                  </div>
                  <span class="small text-muted">${placedIds.has(mw.id) ? 'Active' : 'Installed'}</span>
                </div>
              `;
            });
            html += '</div><p class="small text-muted mb-0 mt-2"><i class="bi bi-shop me-1" aria-hidden="true"></i>Marketplace widgets render via the app\'s own surface. Install / remove from the marketplace.</p>';
          }
          if (!html) {
            listEl.innerHTML = '<p class="text-muted small mb-0">No more widgets available. Hide a widget from the ⋮ menu on any card to restore it here later.</p>';
            return;
          }
          listEl.innerHTML = html;

          // Restore hidden widgets
          listEl.querySelectorAll('[data-restore-widget-id]').forEach((btn) => {
            btn.addEventListener('click', function () {
              const wid = this.getAttribute('data-restore-widget-id');
              if (!wid) return;
              const idx = hiddenWidgetIds.indexOf(wid);
              if (idx >= 0) {
                hiddenWidgetIds.splice(idx, 1);
                columns.forEach((col) => {
                  const el = col.querySelector(`[data-widget-id="${wid}"]`);
                  if (el) { el.classList.remove('dash-widget-hidden'); el.style.display = ''; }
                });
                closeModal();
                saveLayout();
                showToast('Widget restored');
              }
            });
          });

          // Add discoverable widget: persist intent via __settings__.requested_widget_ids,
          // surface a hint that a page refresh will materialize the widget (server-side
          // dashboard-template renderer reads requested_widget_ids on next render).
          listEl.querySelectorAll('[data-add-widget-id]').forEach((btn) => {
            btn.addEventListener('click', function () {
              const wid = this.getAttribute('data-add-widget-id');
              if (!wid) return;
              fetch(layoutUrl(page), { credentials: 'include' })
                .then((r) => (r.ok ? r.json() : null))
                .then((current) => {
                  const layout = (current && current.layout) || {};
                  const settings = Object.assign({}, layout.__settings__ || {});
                  const requested = Array.isArray(settings.requested_widget_ids) ? settings.requested_widget_ids.slice() : [];
                  if (requested.indexOf(wid) < 0) requested.push(wid);
                  settings.requested_widget_ids = requested;
                  const payload = { items: (layout.items || []), __settings__: settings };
                  return fetch(layoutUrl(page), {
                    method: 'PUT',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body: JSON.stringify({ layout: payload }),
                  });
                })
                .then((r) => {
                  closeModal();
                  if (r && r.ok) showToast('Widget queued — refresh to view.');
                  else showToast('Could not queue widget.', 'error', true);
                })
                .catch(() => showToast('Could not queue widget.', 'error', true));
            });
          });

          // Configure cockpit section: open the cockpit configure page filtered to that section
          listEl.querySelectorAll('[data-cockpit-configure-id]').forEach((btn) => {
            btn.addEventListener('click', function () {
              const cid = this.getAttribute('data-cockpit-configure-id') || '';
              const sectionId = cid.replace(/^cockpit-[^-]+-/, '');
              closeModal();
              window.location.href = `/siteconfig/super/configure/cockpit/?section=${encodeURIComponent(sectionId)}`;
            });
          });

          // Promote cockpit section to live on this dashboard. Writes to
          // __settings__.promoted_cockpit_ids via the existing layout API.
          listEl.querySelectorAll('[data-cockpit-promote-id]').forEach((btn) => {
            btn.addEventListener('click', function () {
              const wid = this.getAttribute('data-cockpit-promote-id');
              if (!wid) return;
              fetch(layoutUrl(page), { credentials: 'include' })
                .then((r) => (r.ok ? r.json() : null))
                .then((current) => {
                  const layout = (current && current.layout) || {};
                  const settings = Object.assign({}, layout.__settings__ || {});
                  const promoted = Array.isArray(settings.promoted_cockpit_ids) ? settings.promoted_cockpit_ids.slice() : [];
                  if (promoted.indexOf(wid) < 0) promoted.push(wid);
                  settings.promoted_cockpit_ids = promoted;
                  const payload = { items: (layout.items || []), __settings__: settings };
                  return fetch(layoutUrl(page), {
                    method: 'PUT',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body: JSON.stringify({ layout: payload }),
                  });
                })
                .then((r) => {
                  closeModal();
                  if (r && r.ok) showToast('Cockpit section promoted — refresh to view.');
                  else showToast('Could not promote cockpit section.', 'error', true);
                })
                .catch(() => showToast('Could not promote cockpit section.', 'error', true));
            });
          });
        })
        .catch(() => {
          listEl.innerHTML = '<p class="text-danger small mb-0">Could not load widgets.</p>';
        });
    }

    document.getElementById('btnAddWidget')?.addEventListener('click', openAddWidgetPalette);

    // Loading state (backend still loads meta and wires controls; we skip applyLayout only)
    const loader = document.createElement('div');
    loader.className = 'small text-muted mb-2';
    loader.id = 'dashboard-layout-loading';
    loader.textContent = 'Loading your layout...';
    layoutRoot.parentNode.insertBefore(loader, layoutRoot);

    // Load current layout + widget metadata
    fetch(layoutUrl(page), { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        const loader = document.getElementById('dashboard-layout-loading');
        if (loader) loader.remove();
        if (!data) return;
        if (Array.isArray(data.widgets)) {
          widgetMetaById = {};
          data.widgets.forEach((w) => {
            widgetMetaById[w.id] = w;
          });
        }
        // Backend: do not reorder DOM (complex nested row/col would break); other pages apply saved layout
        if (data.layout && page !== 'backend') applyLayout(columns, data.layout);

        hiddenWidgetIds = (data.layout && data.layout.__settings__ && data.layout.__settings__.hidden_widget_ids) || [];
        if (!Array.isArray(hiddenWidgetIds)) hiddenWidgetIds = [];
        if (page === 'backend') {
          hiddenWidgetIds = hiddenWidgetIds.filter(function (id) { return BACKEND_ALWAYS_VISIBLE.indexOf(id) < 0; });
        }
        columns.forEach((col) => {
          col.querySelectorAll('[data-widget-id]').forEach((el) => {
            if (hiddenWidgetIds.indexOf(el.dataset.widgetId) >= 0) {
              el.classList.add('dash-widget-hidden');
              el.style.display = 'none';
            }
          });
        });
        if (page === 'backend' && layoutRoot) {
          BACKEND_ALWAYS_VISIBLE.forEach(function (id) {
            var el = layoutRoot.querySelector('[data-widget-id="' + id + '"]');
            if (el) { el.classList.remove('dash-widget-hidden'); el.style.display = ''; }
          });
        }
        pinnedWidgets = (data.layout && data.layout.__settings__ && data.layout.__settings__.pinned_widgets) || [];
        if (!Array.isArray(pinnedWidgets)) pinnedWidgets = [];

        // Apply size/variant/chart_type (defaults + saved) and wire controls.
        const layoutItemsById = {};
        const settingsMeta = (data.layout && data.layout.__settings__ && data.layout.__settings__.widget_meta) || {};
        if (data.layout && Array.isArray(data.layout.items)) {
          data.layout.items.forEach((it) => {
            if (it && it.id) layoutItemsById[it.id] = it;
          });
        }
        columns.forEach((col) => {
          const moveUpDown = (targetEl, delta) => moveWidgetInColumn(col, targetEl, delta, true);
          Array.from(col.querySelectorAll('[data-widget-id]')).forEach((el) => {
            const wid = el.dataset.widgetId;
            const item = Object.assign({}, layoutItemsById[wid] || {}, settingsMeta[wid] || {});
            const meta = widgetMetaById[wid] || {};
            applyPresentation(el, item, meta);
            injectGrip(el, moveUpDown);
            injectControls(el, meta, saveLayout, undefined, page === 'backend' ? BACKEND_ALWAYS_VISIBLE : null);
          });
        });
      })
      .catch(() => {
        const loader = document.getElementById('dashboard-layout-loading');
        if (loader) loader.remove();
        if (page === 'backend') {
          var root = document.getElementById('dashboard-layout');
          if (root && typeof BACKEND_ALWAYS_VISIBLE !== 'undefined') {
            BACKEND_ALWAYS_VISIBLE.forEach(function (id) {
              var el = root.querySelector('[data-widget-id="' + id + '"]');
              if (el) { el.classList.remove('dash-widget-hidden'); el.style.display = ''; }
            });
          }
        }
      });

    let setEditModeFn = null;
    const customizeBtn = document.getElementById('btnCustomizeLayout');
    if (customizeBtn) {
      customizeBtn.addEventListener('click', function () {
        if (setEditModeFn) {
          const active = !layoutRoot.classList.contains('drag-mode');
          setEditModeFn(active);
        } else {
          const toast = document.getElementById('dashboard-layout-toast');
          if (toast) {
            const msg = document.createElement('div');
            msg.className = 'dashboard-layout-toast-item alert alert-warning shadow-sm mb-0';
            msg.textContent = 'Loading...';
            toast.appendChild(msg);
            setTimeout(function () { msg.remove(); }, 1500);
          }
        }
      });
    }

    const isLightMode = page === 'parent';

    loadSortable().then((Sortable) => {
      if (!Sortable && !isLightMode) {
        console.warn('Sortable.js failed to load. Drag-and-drop will not work.');
        return;
      }
      if (isLightMode) return;

      const enableDrag = () => {
        if (sortables.length) {
          return;
        }
        
        columns.forEach((col) => {
          const widgets = Array.from(col.querySelectorAll('[data-widget-id]'));
          if (widgets.length === 0) return; // Skip empty columns
          
          try {
            const sortable = Sortable.create(col, {
              group: 'dashboard-widgets',
              handle: '.dashboard-widget-grip',
              filter: '.dash-widget-controls, .dash-widget-controls *, .widget-meta-control, .widget-meta-control *, button, a, input, select, textarea',
              preventOnFilter: true,
              animation: 150,
              forceFallback: false,
              fallbackOnBody: true,
              swapThreshold: 0.65,
              ghostClass: 'sortable-ghost',
              chosenClass: 'sortable-chosen',
              dragClass: 'sortable-drag',
              onStart: () => {
                preDragSnapshot = snapshotDom();
              },
              onEnd: () => {
                saveLayout({ undoable: true });
              },
            });
            sortables.push(sortable);
          } catch (err) {
            console.warn('Failed to initialize Sortable for column:', col, err);
          }
        });
        
        if (sortables.length > 0) {
          layoutRoot.classList.add('drag-mode');
        } else {
          console.warn('No sortable instances created. Check that widgets have [data-widget-id] attributes.');
        }
      };

      const disableDrag = () => {
        sortables.forEach((inst) => {
          if (inst && inst.destroy) {
            try {
              inst.destroy();
            } catch (err) {
              console.warn('Error destroying Sortable instance:', err);
            }
          }
        });
        sortables = [];
        layoutRoot.classList.remove('drag-mode');
      };

      const customDragEnabled = layoutRoot.dataset.customDragEnabled !== "false";
      const customizeBtnRef = document.getElementById('btnCustomizeLayout');

      function applyColumnLabels(active) {
        const isMulti = columns.length > 1;
        columns.forEach((col) => {
          let label = col.querySelector(':scope > .dashboard-column-label');
          if (active && isMulti) {
            if (!label) {
              label = document.createElement('div');
              label.className = 'dashboard-column-label small text-uppercase text-muted fw-semibold mb-2';
              label.setAttribute('aria-hidden', 'true');
              const rawKey = col.dataset.dashboardColumn || col.dataset.dashboardColumnKey || 'main';
              const baseKey = rawKey.split('#')[0];
              const human = baseKey === 'main' ? 'Main' : baseKey === 'sidebar' ? 'Sidebar' : baseKey === 'bottom' ? 'Bottom' : baseKey.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
              label.textContent = human;
              col.insertBefore(label, col.firstChild);
            }
          } else if (label) {
            label.remove();
          }
        });
      }

      function buildMobileListFallback(active) {
        const root = document.getElementById('dashboard-mobile-reorder-list');
        if (!root) return;
        if (!active) { root.innerHTML = ''; root.classList.add('d-none'); return; }
        root.innerHTML = '';
        root.classList.remove('d-none');
        const heading = document.createElement('div');
        heading.className = 'small text-muted mb-2';
        heading.textContent = 'Tap the up / down arrows to reorder widgets. Layout saves automatically.';
        root.appendChild(heading);
        const list = document.createElement('ol');
        list.className = 'list-group list-group-numbered mb-0';
        const allWidgets = [];
        columns.forEach((col) => {
          Array.from(col.querySelectorAll('[data-widget-id]')).forEach((el) => {
            if (el.classList.contains('dash-widget-hidden') || el.style.display === 'none') return;
            allWidgets.push({ el: el, col: col });
          });
        });
        allWidgets.forEach((entry, idx) => {
          const wid = entry.el.dataset.widgetId;
          const meta = widgetMetaById[wid] || {};
          const name = meta.name || (wid || '').replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
          const li = document.createElement('li');
          li.className = 'list-group-item d-flex justify-content-between align-items-center';
          li.dataset.mobileReorderWidgetId = wid;
          const span = document.createElement('span');
          span.textContent = name;
          li.appendChild(span);
          const group = document.createElement('div');
          group.className = 'btn-group btn-group-sm';
          const up = document.createElement('button');
          up.type = 'button';
          up.className = 'btn btn-outline-secondary';
          up.setAttribute('aria-label', 'Move ' + name + ' up');
          up.innerHTML = '<i class="bi bi-chevron-up" aria-hidden="true"></i>';
          up.disabled = (idx === 0);
          up.addEventListener('click', () => { moveWidgetInColumn(entry.col, entry.el, -1, true); buildMobileListFallback(true); });
          const down = document.createElement('button');
          down.type = 'button';
          down.className = 'btn btn-outline-secondary';
          down.setAttribute('aria-label', 'Move ' + name + ' down');
          down.innerHTML = '<i class="bi bi-chevron-down" aria-hidden="true"></i>';
          down.disabled = (idx === allWidgets.length - 1);
          down.addEventListener('click', () => { moveWidgetInColumn(entry.col, entry.el, 1, true); buildMobileListFallback(true); });
          group.appendChild(up);
          group.appendChild(down);
          li.appendChild(group);
          list.appendChild(li);
        });
        root.appendChild(list);
      }

      function setEditMode(active) {
        const instructions = document.getElementById('dashboard-customize-instructions');
        const btn = document.getElementById('btnCustomizeLayout');
        if (instructions) instructions.classList.toggle('d-none', !active);
        if (btn) {
          btn.classList.toggle('active', !!active);
          btn.setAttribute('aria-pressed', active ? 'true' : 'false');
          btn.innerHTML = (active ? '<i class="bi bi-check2 me-1"></i>Done' : '<i class="bi bi-grid-3x3-gap me-1"></i>Customize layout');
          if (active) {
            try {
              if (localStorage.getItem('dashboard-customize-hint-seen') !== '1') {
                var hint = document.createElement('div');
                hint.className = 'alert alert-light border small mt-2';
                hint.innerHTML = 'Drag cards by the grip handle to reorder. Use move up/down controls on mobile. <button type="button" class="btn-close btn-sm float-end" aria-label="Dismiss"></button>';
                hint.querySelector('.btn-close').addEventListener('click', function () {
                  try { localStorage.setItem('dashboard-customize-hint-seen', '1'); } catch (e) {}
                  hint.remove();
                });
                if (instructions && instructions.parentNode) instructions.parentNode.insertBefore(hint, instructions.nextSibling);
              }
            } catch (e) {}
          }
        }
        if (dragToggle) dragToggle.checked = !!active;
        applyColumnLabels(!!active);
        buildMobileListFallback(!!active);
        if (layoutRoot) layoutRoot.classList.toggle('dashboard-edit-mode-active', !!active);
        if (active) enableDrag(); else disableDrag();
      }
      setEditModeFn = setEditMode;

      if (customizeBtnRef) {
        const urlParams = new URLSearchParams(window.location.search);
        const backendPage = page === 'backend';
        const startActive = urlParams.get('customize') === '1' || (!backendPage && (dragToggle && !!dragToggle.checked)) || false;
        if (startActive) setEditMode(true); else setEditMode(false);
      } else {
        const startEnabled = dragToggle ? !!dragToggle.checked : customDragEnabled;
        if (startEnabled) setTimeout(() => enableDrag(), 150);
        if (dragToggle) {
          dragToggle.addEventListener('change', () => {
            if (dragToggle.checked) setTimeout(() => enableDrag(), 50);
            else disableDrag();
          });
        } else if (customDragEnabled) {
          setTimeout(() => enableDrag(), 250);
        }
      }
    });
  }

  ready(() => {
    // Wait a bit for body dataset to be set by inline scripts
    setTimeout(() => {
      const page = (document.body.dataset.dashboardPage || '').toLowerCase();
      initDragDrop(page);
    }, 50);
  });
})();

