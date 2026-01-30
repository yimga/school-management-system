(function () {
  const ready = (fn) => (document.readyState !== 'loading' ? fn() : document.addEventListener('DOMContentLoaded', fn));

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  async function loadSortable() {
    if (window.Sortable) return window.Sortable;
    return new Promise((resolve) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js';
      s.async = true;
      s.onload = () => resolve(window.Sortable);
      s.onerror = () => resolve(null);
      document.head.appendChild(s);
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

  function injectGrip(el) {
    if (el.querySelector('.dashboard-widget-grip')) return;
    const grip = document.createElement('div');
    grip.className = 'dashboard-widget-grip';
    grip.setAttribute('aria-label', 'Drag to reorder');
    grip.setAttribute('title', 'Drag to reorder');
    grip.innerHTML = '<span class="dashboard-widget-grip-dots" aria-hidden="true">⋮⋮</span>';
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

  function injectControls(el, meta, onChange) {
    if (el.dataset.widgetControlsInjected === '1') return;
    el.dataset.widgetControlsInjected = '1';

    const allowedSizes = (meta && meta.allowed_sizes) || ['sm', 'md', 'lg'];
    const allowedVariants = (meta && meta.allowed_variants) || ['default', 'compact', 'flat'];
    const isChartWidget = (meta && meta.widget_type) === 'chart';

    el.classList.add('dash-widget');
    injectGrip(el);

    let menuRows = `
      <div class="dash-widget-row">
        <label>Size</label>
        <select class="dash-widget-size"></select>
      </div>
      <div class="dash-widget-row">
        <label>Style</label>
        <select class="dash-widget-variant"></select>
      </div>
    `;
    if (isChartWidget) {
      menuRows += `
      <div class="dash-widget-row">
        <label>Chart</label>
        <select class="dash-widget-chart-type"></select>
      </div>
      `;
    }

    const controls = document.createElement('div');
    controls.className = 'dash-widget-controls';
    controls.innerHTML = `
      <button type="button" class="dash-widget-gear" aria-label="Widget settings" title="Widget settings">⋯</button>
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

    sizeSelect.value = normalizeSize(el.dataset.widgetSize) || 'md';
    variantSelect.value = normalizeVariant(el.dataset.widgetVariant) || 'default';
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

    sizeSelect.addEventListener('change', () => {
      el.dataset.widgetSize = sizeSelect.value;
      onChange();
    });
    variantSelect.addEventListener('change', () => {
      el.dataset.widgetVariant = variantSelect.value;
      onChange();
    });
    if (isChartWidget && chartTypeSelect) {
      chartTypeSelect.addEventListener('change', () => {
        el.dataset.widgetChartType = chartTypeSelect.value;
        if (window.dashboardCharts && typeof window.dashboardCharts.refreshCharts === 'function') {
          window.dashboardCharts.refreshCharts();
        }
        onChange();
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
    
    ensureColumnKeys(columns);

    let widgetMetaById = {};
    const dragToggle = document.getElementById('toggleLayoutDrag') || document.getElementById('toggleCustomize');
    let sortables = [];

    function showToast(message) {
      const container = document.getElementById('dashboard-layout-toast');
      if (!container) return;
      const toast = document.createElement('div');
      toast.className = 'dashboard-layout-toast-item alert alert-success shadow-sm mb-0';
      toast.setAttribute('role', 'status');
      toast.textContent = message;
      container.appendChild(toast);
      setTimeout(() => toast.remove(), 2500);
    }

    const saveLayout = () => {
      const itemsPayload = collectLayout(columns);
      const widgetMeta = collectWidgetMeta(columns);
      fetch(`/api/dashboard/layout/${page}/`, { credentials: 'include' })
        .then((r) => (r.ok ? r.json() : null))
        .then((current) => {
          const layout = (current && current.layout) || {};
          const settings = Object.assign({}, layout.__settings__ || {});
          settings.widget_meta = Object.assign({}, settings.widget_meta || {}, widgetMeta);
          const payload = {
            items: itemsPayload.items,
            __settings__: settings,
          };
          return fetch(`/api/dashboard/layout/${page}/`, {
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
          if (r && r.ok) showToast('Layout saved');
        })
        .catch(() => {});
    };

    const resetLayout = () => {
      fetch(`/api/dashboard/layout/${page}/`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'X-CSRFToken': getCsrfToken() },
      })
        .then((r) => {
          if (r && r.ok) return fetch(`/api/dashboard/layout/${page}/`, { credentials: 'include' });
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

    // Load current layout + widget metadata
    fetch(`/api/dashboard/layout/${page}/`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        if (Array.isArray(data.widgets)) {
          widgetMetaById = {};
          data.widgets.forEach((w) => {
            widgetMetaById[w.id] = w;
          });
        }
        if (data.layout) applyLayout(columns, data.layout);

        // Apply size/variant/chart_type (defaults + saved) and wire controls.
        const layoutItemsById = {};
        const settingsMeta = (data.layout && data.layout.__settings__ && data.layout.__settings__.widget_meta) || {};
        if (data.layout && Array.isArray(data.layout.items)) {
          data.layout.items.forEach((it) => {
            if (it && it.id) layoutItemsById[it.id] = it;
          });
        }
        columns.forEach((col) => {
          Array.from(col.querySelectorAll('[data-widget-id]')).forEach((el) => {
            const wid = el.dataset.widgetId;
            const item = Object.assign({}, layoutItemsById[wid] || {}, settingsMeta[wid] || {});
            const meta = widgetMetaById[wid] || {};
            applyPresentation(el, item, meta);
            injectGrip(el);
            injectControls(el, meta, saveLayout);
          });
        });
      })
      .catch(() => {});

    function setEditMode(active) {
      const instructions = document.getElementById('dashboard-customize-instructions');
      const btn = document.getElementById('btnCustomizeLayout');
      if (instructions) instructions.classList.toggle('d-none', !active);
      if (btn) {
        btn.classList.toggle('active', !!active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.innerHTML = (active ? '<i class="bi bi-check2 me-1"></i>Done' : '<i class="bi bi-grid-3x3-gap me-1"></i>Customize layout');
      }
      if (dragToggle) dragToggle.checked = !!active;
      if (active) enableDrag(); else disableDrag();
    }

    loadSortable().then((Sortable) => {
      if (!Sortable) {
        console.warn('Sortable.js failed to load. Drag-and-drop will not work.');
        return;
      }

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
              onEnd: () => {
                saveLayout();
              },
            });
            sortables.push(sortable);
          } catch (err) {
            console.warn('Failed to initialize Sortable for column:', col, err);
          }
        });
        
        if (sortables.length > 0) {
          layoutRoot.classList.add('drag-mode');
          console.log(`Drag-and-drop enabled for ${sortables.length} column(s)`);
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
      const customizeBtn = document.getElementById('btnCustomizeLayout');

      if (customizeBtn) {
        customizeBtn.addEventListener('click', () => {
          const active = !layoutRoot.classList.contains('drag-mode');
          setEditMode(active);
        });
        const urlParams = new URLSearchParams(window.location.search);
        const startActive = urlParams.get('customize') === '1' || (dragToggle && !!dragToggle.checked) || false;
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
