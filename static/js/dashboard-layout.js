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

  function injectGrip(el) {
    if (el.querySelector('.dashboard-widget-grip')) return;
    const grip = document.createElement('div');
    grip.className = 'dashboard-widget-grip';
    grip.setAttribute('aria-label', 'Drag to reorder');
    grip.setAttribute('title', 'Drag to reorder');
    grip.innerHTML = '<span class="dashboard-widget-grip-dots" aria-hidden="true">⋮⋮</span>';
    el.insertBefore(grip, el.firstChild);
  }

  function injectControls(el, meta, onChange) {
    if (el.dataset.widgetControlsInjected === '1') return;
    el.dataset.widgetControlsInjected = '1';

    const allowedSizes = (meta && meta.allowed_sizes) || ['sm', 'md', 'lg'];
    const allowedVariants = (meta && meta.allowed_variants) || ['default', 'compact', 'flat'];

    el.classList.add('dash-widget');
    injectGrip(el);

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

    const TOAST_DURATION = 2500;
    const PLACEHOLDER_CLASS = 'dashboard-column-placeholder';

    function showToast(message, type) {
      type = type || 'success';
      const container = document.getElementById('dashboard-layout-toast');
      if (!container) return;
      const toast = document.createElement('div');
      toast.className = 'dashboard-layout-toast-item alert shadow-sm mb-0 ' +
        (type === 'error' ? 'alert-danger' : type === 'info' ? 'alert-info' : 'alert-success');
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      toast.textContent = message;
      container.appendChild(toast);
      setTimeout(() => toast.remove(), TOAST_DURATION);
    }

    function showSavingToast() {
      const container = document.getElementById('dashboard-layout-toast');
      if (!container) return null;
      clearSavingToast();
      const el = document.createElement('div');
      el.className = 'dashboard-layout-toast-item dashboard-layout-toast-saving alert alert-secondary shadow-sm mb-0';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.textContent = 'Saving…';
      container.appendChild(el);
      return el;
    }

    function clearSavingToast() {
      const container = document.getElementById('dashboard-layout-toast');
      if (!container) return;
      container.querySelectorAll('.dashboard-layout-toast-saving').forEach((t) => t.remove());
    }

    const saveLayout = () => {
      const itemsPayload = collectLayout(columns);
      const savingEl = showSavingToast();
      fetch(`/api/dashboard/layout/${page}/`, { credentials: 'include' })
        .then((r) => (r.ok ? r.json() : null))
        .then((current) => {
          const layout = (current && current.layout) || {};
          const settings = layout.__settings__ || {};
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
          clearSavingToast();
          if (r && r.ok) showToast('Layout saved');
          else showToast('Could not save layout', 'error');
        })
        .catch(() => {
          clearSavingToast();
          showToast('Could not save layout', 'error');
        });
    };

    function resetLayout() {
      const savingEl = showSavingToast();
      fetch(`/api/dashboard/layout/${page}/`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'X-CSRFToken': getCsrfToken() },
      })
        .then((r) => {
          if (!r || !r.ok) throw new Error('Reset failed');
          return fetch(`/api/dashboard/layout/${page}/`, { credentials: 'include' });
        })
        .then((r) => (r && r.ok ? r.json() : null))
        .then((data) => {
          clearSavingToast();
          if (data && data.layout) applyLayout(columns, data.layout);
          showToast('Layout reset to default');
        })
        .catch(() => {
          clearSavingToast();
          showToast('Could not reset layout', 'error');
        });
    }

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
            injectGrip(el);
            injectControls(el, meta, saveLayout);
          });
        });
      })
      .catch(() => {});

    function setEditMode(active) {
      const instructions = document.getElementById('dashboard-customize-instructions');
      const allBtns = document.querySelectorAll('.js-btn-customize-layout');
      if (instructions) instructions.classList.toggle('d-none', !active);
      allBtns.forEach((btn) => {
        btn.classList.toggle('active', !!active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        if (btn.id === 'btnCustomizeLayout') {
          btn.innerHTML = (active ? '<i class="bi bi-check2 me-1"></i>Done' : '<i class="bi bi-grid-3x3-gap me-1"></i>Customize layout');
        } else if (btn.id === 'sidebar-customize-layout-trigger') {
          btn.innerHTML = (active ? '<i class="bi bi-check2 me-2"></i>Done' : '<i class="bi bi-grid-3x3-gap me-2"></i>Customize layout');
        }
      });
      if (dragToggle) dragToggle.checked = !!active;
      if (active) enableDrag(); else disableDrag();
    }

    loadSortable().then((Sortable) => {
      if (!Sortable) {
        console.warn('Sortable.js failed to load. Drag-and-drop will not work.');
        return;
      }

      function injectEmptyColumnPlaceholder(col) {
        if (col.querySelector('.' + PLACEHOLDER_CLASS)) return;
        const placeholder = document.createElement('div');
        placeholder.className = PLACEHOLDER_CLASS;
        placeholder.setAttribute('aria-hidden', 'true');
        placeholder.textContent = 'Drop widgets here';
        col.appendChild(placeholder);
      }

      function removeAllPlaceholders() {
        layoutRoot.querySelectorAll('.' + PLACEHOLDER_CLASS).forEach((el) => el.remove());
      }

      const enableDrag = () => {
        if (sortables.length) {
          return;
        }

        columns.forEach((col) => {
          const widgets = Array.from(col.querySelectorAll('[data-widget-id]'));
          if (widgets.length === 0) injectEmptyColumnPlaceholder(col);

          try {
            const sortable = Sortable.create(col, {
              group: 'dashboard-widgets',
              handle: '.dashboard-widget-grip',
              filter: '.dash-widget-controls, .dash-widget-controls *, .widget-meta-control, .widget-meta-control *, button, a, input, select, textarea, .' + PLACEHOLDER_CLASS,
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
                columns.forEach((c) => {
                  const count = c.querySelectorAll('[data-widget-id]').length;
                  const ph = c.querySelector('.' + PLACEHOLDER_CLASS);
                  if (count === 0 && !ph) injectEmptyColumnPlaceholder(c);
                  if (count > 0 && ph) ph.remove();
                });
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
        removeAllPlaceholders();
        layoutRoot.classList.remove('drag-mode');
      };

      const customDragEnabled = layoutRoot.dataset.customDragEnabled !== "false";
      const customizeBtns = document.querySelectorAll('.js-btn-customize-layout');

      function onCustomizeClick() {
        const active = !layoutRoot.classList.contains('drag-mode');
        setEditMode(active);
      }

      document.querySelectorAll('.js-reset-dashboard-layout').forEach((btn) => {
        btn.addEventListener('click', () => resetLayout());
      });

      if (customizeBtns.length) {
        customizeBtns.forEach((btn) => btn.addEventListener('click', onCustomizeClick));
        const startActive = dragToggle ? !!dragToggle.checked : false;
        if (!startActive) setEditMode(false);
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
