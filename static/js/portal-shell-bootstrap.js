/**
 * Portal shell bootstrap — header search filtering + sidebar resize/collapse.
 *
 * History:
 *   - Originally handled theme toggle + Ctrl+K + search + sidebar.
 *   - 2026-05-12: theme toggle moved to `theme-preference-bootstrap.js` (canonical
 *     Light/Dark/System bootstrap with prefers-color-scheme live response) and
 *     `RMCTheme` API. Legacy theme handler retired here to avoid duplicate
 *     `data-theme` writes and the System-mode collapse bug.
 *   - 2026-05-12: Ctrl+K shortcut moved to `rmc-command-palette.js` (.rmc-cmdk
 *     global Spotlight-style palette). The header search input still works as
 *     a chrome affordance and on focus/input — it just no longer claims Ctrl+K.
 *
 * Externalised from portal_base.html so the shell is CSP-friendly (no inline
 * executable script).
 */
(function () {
  'use strict';

  // -- Header search bar (fetches /api/search/ and renders inline results) --
  // Ctrl+K is intentionally NOT bound here — that's owned by rmc-command-palette.js
  // (the global ⌘K palette is more powerful than this single-input search).
  document.addEventListener('DOMContentLoaded', function () {
    var searchInput = document.getElementById('headerSearchInput');
    var resultsEl = document.getElementById('headerSearchResults');
    if (!searchInput || !resultsEl) return;

    var searchTimeout;

    function showResults(html) {
      resultsEl.innerHTML = html;
      resultsEl.style.display = html ? 'block' : 'none';
    }

    function hideResults() {
      setTimeout(function () { showResults(''); }, 150);
    }

    searchInput.addEventListener('input', function () {
      var q = (this.value || '').trim();
      clearTimeout(searchTimeout);
      if (q.length < 2) {
        showResults('');
        return;
      }
      searchTimeout = setTimeout(function () {
        fetch('/api/search/?q=' + encodeURIComponent(q) + '&limit=8', { credentials: 'same-origin' })
          .then(function (r) {
            if (!r.ok) throw new Error('Search failed');
            return r.json();
          })
          .then(function (data) {
            var esc = function (t) { var d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; };
            var items = data.results || [];
            if (items.length === 0) {
              showResults('<div class="search-result-empty">No results for "' + esc(q.length > 20 ? q.slice(0, 20) + '...' : q) + '"</div>');
            } else {
              showResults(items.map(function (item) {
                var title = esc(item.title || item.label || '');
                var desc = item.description ? ' <span class="search-result-muted">' + esc(item.description) + '</span>' : '';
                var url = (item.url || '#').replace(/"/g, '&quot;');
                return '<a class="search-result-item" href="' + url + '" role="option"><i class="bi ' + (item.icon || 'bi-circle') + ' me-2"></i>' + title + desc + '</a>';
              }).join(''));
            }
          })
          .catch(function () {
            showResults('<div class="search-result-error">Search failed. Try again.</div>');
          });
      }, 250);
    });

    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        showResults('');
        this.blur();
      } else if (e.key === 'Enter') {
        var first = resultsEl.querySelector('.search-result-item');
        if (first) {
          first.click();
          showResults('');
        }
      }
    });

    searchInput.addEventListener('blur', function (e) {
      var rel = e.relatedTarget;
      if (rel && resultsEl.contains(rel)) return;
      hideResults();
    });
  });

  // -- Resizable + collapsible sidebar --
  document.addEventListener('DOMContentLoaded', function () {
    var handle = document.querySelector('.portal-resize-handle');
    var root = document.documentElement;
    var MIN = 200;
    var MAX = 420;
    var KEY = 'portal-sidebar-width';

    function px(v) { return Math.round(v) + 'px'; }
    function clamp(v) { return Math.max(MIN, Math.min(MAX, v)); }

    function loadWidth() {
      var w = parseInt(localStorage.getItem(KEY), 10);
      if (w && w >= MIN && w <= MAX) root.style.setProperty('--portal-sidebar-width', px(w));
    }
    loadWidth();

    var sidebarCol = document.getElementById('portal-sidebar-col');
    var collapseKey = 'portal-sidebar-collapsed';
    var collapseKeys = [collapseKey];
    var collapseButtons = Array.from(document.querySelectorAll('.portal-sidebar-collapse-toggle, .js-sidebar-toggle'));

    function updateCollapseButtons(collapsed) {
      collapseButtons.forEach(function (btn) {
        btn.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
        btn.setAttribute('aria-expanded', String(!collapsed));
        btn.setAttribute('title', collapsed ? 'Expand sidebar' : 'Collapse sidebar to icons');
        var icon = btn.querySelector('.bi-layout-sidebar-inset, .bi-layout-sidebar-inset-reverse');
        if (icon) {
          icon.classList.toggle('bi-layout-sidebar-inset', !collapsed);
          icon.classList.toggle('bi-layout-sidebar-inset-reverse', collapsed);
        }
        var label = btn.querySelector('[data-sidebar-toggle-label]');
        if (label) {
          label.textContent = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
        }
      });
    }

    function setSidebarCollapsed(collapsed) {
      if (!sidebarCol) return;
      sidebarCol.classList.toggle('portal-sidebar-collapsed', collapsed);
      collapseKeys.forEach(function (k) {
        localStorage.setItem(k, collapsed ? 'true' : 'false');
      });
      updateCollapseButtons(collapsed);
    }

    function loadCollapsed() {
      if (!sidebarCol) return;
      var collapsed = false;
      for (var i = 0; i < collapseKeys.length; i++) {
        if (localStorage.getItem(collapseKeys[i]) === 'true') {
          collapsed = true;
          break;
        }
      }
      setSidebarCollapsed(collapsed);
    }
    loadCollapsed();
    collapseButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (!sidebarCol) return;
        var collapsed = !sidebarCol.classList.contains('portal-sidebar-collapsed');
        setSidebarCollapsed(collapsed);
      });
    });

    if (handle) {
      handle.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        e.preventDefault();
        var startX = e.clientX;
        var startW = parseInt(getComputedStyle(root).getPropertyValue('--portal-sidebar-width'), 10) || 280;

        function move(e) {
          var dx = e.clientX - startX;
          var newW = clamp(startW + dx);
          root.style.setProperty('--portal-sidebar-width', px(newW));
        }
        function up() {
          var w = parseInt(getComputedStyle(root).getPropertyValue('--portal-sidebar-width'), 10);
          localStorage.setItem(KEY, String(w));
          document.removeEventListener('mousemove', move);
          document.removeEventListener('mouseup', up);
          document.body.style.cursor = '';
          document.body.style.userSelect = '';
        }

        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
      });
    }
  });
})();
