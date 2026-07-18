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
 *   - 2026-07-18: typeahead uses class API (not inline display), listbox keyboard
 *     nav, and stays anchored under the search input (never a fullscreen overlay).
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
    var activeIndex = -1;

    function openPanel() {
      resultsEl.classList.remove('header-search-dropdown--hidden');
      resultsEl.setAttribute('aria-expanded', 'true');
      searchInput.setAttribute('aria-expanded', 'true');
    }

    function closePanel() {
      resultsEl.classList.add('header-search-dropdown--hidden');
      resultsEl.innerHTML = '';
      resultsEl.setAttribute('aria-expanded', 'false');
      searchInput.setAttribute('aria-expanded', 'false');
      activeIndex = -1;
      searchInput.removeAttribute('aria-activedescendant');
    }

    function showResults(html) {
      resultsEl.innerHTML = html || '';
      if (html) {
        openPanel();
      } else {
        closePanel();
      }
      activeIndex = -1;
    }

    function optionNodes() {
      return Array.prototype.slice.call(
        resultsEl.querySelectorAll('.search-result-item')
      );
    }

    function setActive(index) {
      var options = optionNodes();
      options.forEach(function (el, i) {
        var on = i === index;
        el.classList.toggle('is-active', on);
        el.setAttribute('aria-selected', on ? 'true' : 'false');
        if (on) {
          searchInput.setAttribute('aria-activedescendant', el.id);
          el.scrollIntoView({ block: 'nearest' });
        }
      });
      activeIndex = index;
    }

    searchInput.setAttribute('role', 'combobox');
    searchInput.setAttribute('aria-autocomplete', 'list');
    searchInput.setAttribute('aria-controls', 'headerSearchResults');
    searchInput.setAttribute('aria-expanded', 'false');
    resultsEl.setAttribute('role', 'listbox');

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
        resultsEl.innerHTML = '<div class="search-result-empty" role="status">Searching…</div>';
        openPanel();
        fetch(searchBase + searchSep + 'q=' + encodeURIComponent(q) + '&limit=8', { credentials: 'same-origin' })
          .then(function (r) {
            if (!r.ok) throw new Error('Search failed');
            return r.json();
          })
          .then(function (data) {
            var esc = function (t) { var d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; };
            var items = data.results || [];
            if (items.length === 0) {
              showResults('<div class="search-result-empty" role="status">No results for "' + esc(q.length > 20 ? q.slice(0, 20) + '...' : q) + '"</div>');
            } else {
              showResults(items.map(function (item, idx) {
                var title = esc(item.title || item.label || '');
                var desc = item.description ? ' <span class="search-result-muted">' + esc(item.description) + '</span>' : '';
                var url = (item.url || '#').replace(/"/g, '&quot;');
                var id = 'headerSearchOption-' + idx;
                return '<a id="' + id + '" class="search-result-item" href="' + url + '" role="option" aria-selected="false"><i class="bi ' + (item.icon || 'bi-circle') + ' me-2" aria-hidden="true"></i>' + title + desc + '</a>';
              }).join(''));
            }
          })
          .catch(function () {
            showResults('<div class="search-result-error" role="alert">Search failed. Try again.</div>');
          });
      }, 250);
    });

    searchInput.addEventListener('keydown', function (e) {
      var options = optionNodes();
      if (e.key === 'Escape') {
        showResults('');
        this.blur();
        return;
      }
      if (e.key === 'ArrowDown') {
        if (!options.length) return;
        e.preventDefault();
        setActive(activeIndex < options.length - 1 ? activeIndex + 1 : 0);
        return;
      }
      if (e.key === 'ArrowUp') {
        if (!options.length) return;
        e.preventDefault();
        setActive(activeIndex > 0 ? activeIndex - 1 : options.length - 1);
        return;
      }
      if (e.key === 'Enter') {
        var target = activeIndex >= 0 ? options[activeIndex] : options[0];
        if (target) {
          e.preventDefault();
          target.click();
          showResults('');
        }
      }
    });

    searchInput.addEventListener('blur', function (e) {
      var rel = e.relatedTarget;
      if (rel && resultsEl.contains(rel)) return;
      setTimeout(function () { showResults(''); }, 150);
    });

    document.addEventListener('click', function (e) {
      if (!searchInput.contains(e.target) && !resultsEl.contains(e.target)) {
        showResults('');
      }
    });
  });

  // Sidebar rail + resize delegated to static/js/rmc-nav-sidebar.js (v4.02.1).
})();
