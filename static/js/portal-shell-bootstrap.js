// Portal shell bootstrap: theme toggle, global Ctrl+K search, sidebar resize/collapse.
// Externalised from portal_base.html so the shell is CSP-friendly (no inline executable script).
(function () {
  'use strict';

  // -- Theme Toggle: light / dark / system (persisted in localStorage) ----
  document.addEventListener('DOMContentLoaded', function () {
    var themeToggle = document.getElementById('themeToggle');
    var htmlElement = document.documentElement;

    function getSystemTheme() {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    function resolveTheme(stored) {
      if (stored === 'system') return getSystemTheme();
      return stored === 'dark' ? 'dark' : 'light';
    }
    function updateMetaThemeColor(resolved) {
      var meta = document.querySelector('meta[name="theme-color"]');
      if (!meta) return;
      var prop = resolved === 'dark' ? '--meta-theme-color-dark' : '--meta-theme-color-light';
      var value = getComputedStyle(htmlElement).getPropertyValue(prop).trim();
      if (value) meta.setAttribute('content', value);
    }
    function updateThemeIcon(stored, resolved) {
      if (!themeToggle) return;
      var icon = themeToggle.querySelector('i');
      if (!icon) return;
      icon.classList.remove('bi-moon-stars', 'bi-sun-fill', 'bi-circle-half');
      if (stored === 'system') {
        icon.classList.add('bi-circle-half');
        themeToggle.setAttribute('title', 'Theme: System (' + resolved + ')');
      } else if (resolved === 'dark') {
        icon.classList.add('bi-sun-fill');
        themeToggle.setAttribute('title', 'Switch to light');
      } else {
        icon.classList.add('bi-moon-stars');
        themeToggle.setAttribute('title', 'Switch to dark');
      }
    }
    function applyTheme(stored) {
      var resolved = resolveTheme(stored);
      htmlElement.setAttribute('data-theme', resolved);
      htmlElement.setAttribute('data-bs-theme', resolved);
      updateThemeIcon(stored, resolved);
      updateMetaThemeColor(resolved);
    }
    function cycleTheme() {
      var key = 'runmycampus-theme-preference';
      var stored = localStorage.getItem(key) || 'light';
      var next = stored === 'light' ? 'dark' : (stored === 'dark' ? 'system' : 'light');
      localStorage.setItem(key, next);
      applyTheme(next);
    }

    var key = 'runmycampus-theme-preference';
    var stored = localStorage.getItem(key);
    applyTheme(stored || 'light');
    if (themeToggle) themeToggle.addEventListener('click', cycleTheme);

    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
        if ((localStorage.getItem('runmycampus-theme-preference') || 'light') === 'system') applyTheme('system');
      });
    }
  });

  // -- Global Search Bar (Ctrl+K) — fetches /api/search/ and shows results --
  document.addEventListener('DOMContentLoaded', function () {
    var searchInput = document.getElementById('headerSearchInput');
    var resultsEl = document.getElementById('headerSearchResults');
    if (!searchInput || !resultsEl) return;

    var searchTimeout;

    function showResults(html) {
      resultsEl.innerHTML = html;
      resultsEl.style.display = html ? 'block' : 'none';
      searchInput.setAttribute('aria-expanded', html ? 'true' : 'false');
    }

    function hideResults() {
      setTimeout(function () { showResults(''); }, 150);
    }

    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    });

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
