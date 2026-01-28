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
        items.push({
          id: el.dataset.widgetId,
          column: columnKey,
          order: idx,
          size: el.dataset.widgetSize || null,
          variant: el.dataset.widgetVariant || null,
        });
      });
    });
    return { items };
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
  }

  function injectControls(el, meta, onChange) {
    if (el.dataset.widgetControlsInjected === '1') return;
    el.dataset.widgetControlsInjected = '1';

    const allowedSizes = (meta && meta.allowed_sizes) || ['sm', 'md', 'lg'];
    const allowedVariants = (meta && meta.allowed_variants) || ['default', 'compact', 'flat'];

    // Make sure the widget can anchor the control button.
    el.classList.add('dash-widget');

    const controls = document.createElement('div');
    controls.className = 'dash-widget-controls';
    controls.innerHTML = `
      <button type="button" class="dash-widget-gear" aria-label="Widget settings" title="Widget settings">⋯</button>
      <div class="dash-widget-menu" aria-hidden="true">
        <div class="dash-widget-row">
          <label>Size</label>
          <select class="dash-widget-size"></select>
        </div>
        <div class="dash-widget-row">
          <label>Style</label>
          <select class="dash-widget-variant"></select>
        </div>
      </div>
    `;

    const sizeSelect = controls.querySelector('.dash-widget-size');
    const variantSelect = controls.querySelector('.dash-widget-variant');
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

    sizeSelect.value = normalizeSize(el.dataset.widgetSize) || 'md';
    variantSelect.value = normalizeVariant(el.dataset.widgetVariant) || 'default';

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
        else page = 'backend'; // default
      }
    }
    
    if (!page) return;
    
    ensureColumnKeys(columns);

    let widgetMetaById = {};
    const dragToggle = document.getElementById('toggleLayoutDrag') || document.getElementById('toggleCustomize');
    let sortables = [];

    const saveLayout = () => {
      const payload = collectLayout(columns);
      fetch(`/api/dashboard/layout/${page}/`, {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({ layout: payload }),
      }).catch(() => {});
    };

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

        // Apply size/variant (defaults + saved) and wire controls.
        const layoutItemsById = {};
        if (data.layout && Array.isArray(data.layout.items)) {
          data.layout.items.forEach((it) => {
            if (it && it.id) layoutItemsById[it.id] = it;
          });
        }
        columns.forEach((col) => {
          Array.from(col.querySelectorAll('[data-widget-id]')).forEach((el) => {
            const item = layoutItemsById[el.dataset.widgetId] || {};
            const meta = widgetMetaById[el.dataset.widgetId] || {};
            applyPresentation(el, item, meta);
            injectControls(el, meta, saveLayout);
          });
        });
      })
      .catch(() => {});

    loadSortable().then((Sortable) => {
      if (!Sortable) {
        console.warn('Sortable.js failed to load. Drag-and-drop will not work.');
        return;
      }

      const enableDrag = () => {
        if (sortables.length) {
          // Already enabled
          return;
        }
        
        columns.forEach((col) => {
          const widgets = Array.from(col.querySelectorAll('[data-widget-id]'));
          if (widgets.length === 0) return; // Skip empty columns
          
          try {
            const sortable = Sortable.create(col, {
              group: 'dashboard-widgets',
              handle: '[data-widget-id]',
              filter: '.dash-widget-controls, .dash-widget-controls *, .widget-meta-control, .widget-meta-control *, button, a, input, select, textarea',
              preventOnFilter: true,
              animation: 150,
              forceFallback: false,
              fallbackOnBody: true,
              swapThreshold: 0.65,
              ghostClass: 'sortable-ghost',
              chosenClass: 'sortable-chosen',
              dragClass: 'sortable-drag',
              onEnd: (evt) => {
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

      // Check if customDragEnabled is set (from dashboard-customizer.js)
      const customDragEnabled = layoutRoot.dataset.customDragEnabled !== "false";
      const startEnabled = dragToggle ? !!dragToggle.checked : customDragEnabled;
      
      if (startEnabled) {
        // Small delay to ensure DOM is ready and other scripts have run
        setTimeout(() => enableDrag(), 150);
      }

      if (dragToggle) {
        dragToggle.addEventListener('change', () => {
          if (dragToggle.checked) {
            setTimeout(() => enableDrag(), 50);
          } else {
            disableDrag();
          }
        });
      } else if (customDragEnabled) {
        // No toggle but drag is enabled: auto-enable after a short delay
        setTimeout(() => enableDrag(), 250);
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
