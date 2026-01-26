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

  function initDragDrop(page) {
    const columns = Array.from(document.querySelectorAll('[data-dashboard-column]'));
    if (!page || !columns.length) return;
    ensureColumnKeys(columns);

    // Load current layout
    fetch(`/api/dashboard/layout/${page}/`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.layout) applyLayout(columns, data.layout);
      })
      .catch(() => {});

    loadSortable().then((Sortable) => {
      if (!Sortable) return;
      columns.forEach((col) => {
        Sortable.create(col, {
          group: 'dashboard-widgets',
          handle: '[data-widget-id]',
          animation: 150,
          onEnd: () => {
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
          },
        });
      });
    });
  }

  ready(() => {
    const page = (document.body.dataset.dashboardPage || '').toLowerCase();
    initDragDrop(page);
  });
})();
