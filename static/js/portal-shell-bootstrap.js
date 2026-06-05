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
        var searchBase = (window.RMCPlatformSurface && window.RMCPlatformSurface.url('search')) || '';
        if (!searchBase) return;
        var searchSep = searchBase.indexOf('?') >= 0 ? '&' : '?';
        fetch(searchBase + searchSep + 'q=' + encodeURIComponent(q) + '&limit=8', { credentials: 'same-origin' })
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

  // Sidebar rail + resize delegated to static/js/rmc-nav-sidebar.js (v4.02.1).
})();
