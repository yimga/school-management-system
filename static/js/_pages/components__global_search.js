document.addEventListener('DOMContentLoaded', function() {
  const searchTrigger = document.getElementById('searchTrigger');
  const searchModal = new bootstrap.Modal(document.getElementById('searchModal'));
  const searchInput = document.getElementById('searchInput');
  const searchClear = document.getElementById('searchClear');
  const searchResultsSection = document.getElementById('searchResultsSection');
  const searchResultItems = document.getElementById('searchResultItems');
  const searchLoading = document.getElementById('searchLoading');
  const searchEmpty = document.getElementById('searchEmpty');
  const searchError = document.getElementById('searchError');
  const recentSearches = document.getElementById('recentSearches');
  const recentItems = document.getElementById('recentItems');
  const clearHistory = document.getElementById('clearHistory');

  let searchTimeout;
  let selectedIndex = -1;

  // Open search with Ctrl+K
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      searchTrigger.click();
    }
  });

  // Open search modal
  searchTrigger.addEventListener('click', function() {
    searchModal.show();
    setTimeout(() => searchInput.focus(), 100);
    loadRecentSearches();
  });

  const searchHelpSection = document.getElementById('searchHelpSection');

  // Search input handler
  searchInput.addEventListener('input', function() {
    const query = this.value.trim();
    
    if (query.length === 0) {
      searchClear.style.display = 'none';
      searchResultsSection.style.display = 'none';
      searchEmpty.style.display = 'none';
      if (searchError) searchError.style.display = 'none';
      recentSearches.style.display = 'block';
      if (searchHelpSection) searchHelpSection.style.display = 'block';
      return;
    }

    searchClear.style.display = 'block';
    recentSearches.style.display = 'none';
    if (searchHelpSection) searchHelpSection.style.display = 'none';

    // Debounce search
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => performSearch(query), 300);
  });

  // Clear search
  searchClear.addEventListener('click', function() {
    searchInput.value = '';
    searchInput.focus();
    searchClear.style.display = 'none';
    searchResultsSection.style.display = 'none';
    searchEmpty.style.display = 'none';
    if (searchError) searchError.style.display = 'none';
    recentSearches.style.display = 'block';
    if (searchHelpSection) searchHelpSection.style.display = 'block';
  });

  // Perform search
  async function performSearch(query) {
    searchLoading.style.display = 'flex';
    searchResultsSection.style.display = 'none';
    searchEmpty.style.display = 'none';
    if (searchError) searchError.style.display = 'none';

    try {
      const response = await fetch(`/api/search/?q=${encodeURIComponent(query)}&story=1`);
      const data = response.ok ? await response.json().catch(() => ({})) : {};

      searchLoading.style.display = 'none';

      if (!response.ok) {
        if (searchError) {
          searchError.querySelector('p').textContent = 'Search temporarily unavailable';
          searchError.style.display = 'block';
        } else {
          searchEmpty.querySelector('p').textContent = 'Search temporarily unavailable';
          searchEmpty.style.display = 'block';
        }
        return;
      }

      if (data.results && data.results.length > 0) {
        renderResults(data.results);
        saveToHistory(query);
      } else {
        searchEmpty.querySelector('p').textContent = 'No results found';
        searchEmpty.style.display = 'block';
      }
    } catch (error) {
      console.error('Search error:', error);
      searchLoading.style.display = 'none';
      if (searchError) {
        searchError.style.display = 'block';
      } else {
        searchEmpty.querySelector('p').textContent = 'Search temporarily unavailable';
        searchEmpty.style.display = 'block';
      }
    }
  }

  function escHtml(s) {
    if (s == null || s === '') return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  // Render search results
  function renderResults(results) {
    searchResultItems.innerHTML = results.map(result => {
      const icon = getIconForType(result.type);
      const color = getColorForType(result.type);
      const story = result.story;
      const storyBlock = story ? `
        <div class="search-story-rows" aria-label="Cross-module summary">
          <div><strong>Academic</strong>${escHtml(story.academic_line)}</div>
          <div><strong>Finance</strong>${escHtml(story.finance_line)}</div>
          <div><strong>Messages</strong>${escHtml(story.communication_line)}</div>
          <div><strong>Attendance</strong>${escHtml(story.attendance_line)}</div>
        </div>
      ` : '';
      const itemClass = story ? 'search-item search-item-story' : 'search-item';
      return `
        <a href="${String(result.url || '#').replace(/"/g, '&quot;')}" class="${itemClass}">
          <div class="d-flex gap-2 w-100 align-items-start">
            <div class="search-item-icon ${color}">
              <i class="bi ${icon}"></i>
            </div>
            <div class="search-item-content flex-grow-1 min-w-0">
              <div class="search-item-title">${highlightQuery(result.title, searchInput.value)}</div>
              <div class="search-item-desc">${escHtml(result.description || '')}</div>
              ${result.meta ? `
                <div class="search-item-meta">
                  ${result.meta.map(m => `<span class="search-item-badge">${escHtml(m)}</span>`).join('')}
                </div>
              ` : ''}
              ${storyBlock}
            </div>
          </div>
        </a>
      `;
    }).join('');

    searchResultsSection.style.display = 'block';

    // Add keyboard navigation
    const items = document.querySelectorAll('.search-item');
    items.forEach((item, index) => {
      item.addEventListener('mouseenter', () => {
        items.forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        selectedIndex = index;
      });
    });
  }

  // Highlight search query in results
  function highlightQuery(text, query) {
    if (!query) return text;
    const regex = new RegExp(`(${query})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
  }

  // Get icon for result type
  function getIconForType(type) {
    const icons = {
      student: 'bi-person',
      teacher: 'bi-person-badge',
      class: 'bi-people',
      invoice: 'bi-receipt',
      report: 'bi-file-text',
      subject: 'bi-book',
    };
    return icons[type] || 'bi-file';
  }

  // Get color for result type
  function getColorForType(type) {
    const colors = {
      student: 'bg-primary',
      teacher: 'bg-success',
      class: 'bg-info',
      invoice: 'bg-warning',
      report: 'bg-secondary',
      subject: 'bg-purple',
    };
    return colors[type] || 'bg-secondary';
  }

  // Load recent searches
  function loadRecentSearches() {
    const recent = JSON.parse(localStorage.getItem('recentSearches') || '[]');
    if (recent.length === 0) {
      recentSearches.style.display = 'none';
      return;
    }

    recentItems.innerHTML = recent.map(search => `
      <div class="search-item" data-query="${search}">
        <div class="search-item-icon bg-secondary">
          <i class="bi bi-clock-history"></i>
        </div>
        <div class="search-item-content">
          <div class="search-item-title">${search}</div>
        </div>
      </div>
    `).join('');

    // Click to search recent item
    document.querySelectorAll('#recentItems .search-item').forEach(item => {
      item.addEventListener('click', function() {
        searchInput.value = this.dataset.query;
        searchInput.dispatchEvent(new Event('input'));
      });
    });
  }

  // Save search to history
  function saveToHistory(query) {
    let recent = JSON.parse(localStorage.getItem('recentSearches') || '[]');
    recent = recent.filter(q => q !== query); // Remove duplicates
    recent.unshift(query);
    recent = recent.slice(0, 5); // Keep only last 5
    localStorage.setItem('recentSearches', JSON.stringify(recent));
  }

  // Clear history
  clearHistory.addEventListener('click', function() {
    localStorage.removeItem('recentSearches');
    recentSearches.style.display = 'none';
  });

  // Keyboard navigation
  searchInput.addEventListener('keydown', function(e) {
    const items = document.querySelectorAll('.search-item');
    
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
      updateSelection(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedIndex = Math.max(selectedIndex - 1, 0);
      updateSelection(items);
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      items[selectedIndex].click();
    }
  });

  function updateSelection(items) {
    items.forEach((item, index) => {
      item.classList.toggle('active', index === selectedIndex);
    });
    if (items[selectedIndex]) {
      items[selectedIndex].scrollIntoView({ block: 'nearest' });
    }
  }
});
