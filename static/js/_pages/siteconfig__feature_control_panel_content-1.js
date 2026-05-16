(function(){
  var pageDataEl=document.getElementById("page-data-siteconfig__feature_control_panel_content-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["siteconfig__feature_control_panel_content-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  const form = document.getElementById('featureControlForm');
  const search = document.getElementById('featureSearch');
  const noResults = document.getElementById('noSearchResults');
  const criticalInputs = form ? form.querySelectorAll('[data-critical="true"]') : [];
  const maintenanceInp = form ? form.querySelector('[name="feature_maintenance_mode"]') : null;
  const currentState = (window.__RMC_PAGE_DATA__["siteconfig__feature_control_panel_content-1"]||{})["var_current_json_safe"];
  const weatherCountrySelect = document.getElementById('weatherCountrySelect');
  const weatherCitySelect = document.getElementById('weatherCitySelect');
  const weatherCitySearch = document.getElementById('weatherCitySearch');
  const weatherLocationPreview = document.getElementById('weatherLocationPreview');
  const weatherTimezonePreview = document.getElementById('weatherTimezonePreview');
  const weatherCityUrl = form ? (form.getAttribute('data-weather-city-url') || '') : '';
  const initialWeatherCityId = weatherCitySelect ? String(weatherCitySelect.value || '') : '';
  let weatherCityDebounce = null;
  let weatherCityFetchToken = 0;
  let searchTimeout = null;

  function syncWeatherCityOptions() {
    if (!weatherCitySelect) return;
    const selectedOpt = weatherCitySelect.options[weatherCitySelect.selectedIndex];
    const label = selectedOpt ? (selectedOpt.dataset.label || selectedOpt.textContent || 'Weather location') : 'Weather location';
    const tz = selectedOpt ? (selectedOpt.dataset.timezone || 'UTC') : 'UTC';
    if (weatherLocationPreview) weatherLocationPreview.textContent = label;
    if (weatherTimezonePreview) weatherTimezonePreview.textContent = tz;
  }

  function renderWeatherCities(cities) {
    if (!weatherCitySelect) return;
    const previous = String(weatherCitySelect.value || initialWeatherCityId || '');
    weatherCitySelect.innerHTML = '';
    if (!cities || !cities.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No matching cities';
      weatherCitySelect.appendChild(opt);
      syncWeatherCityOptions();
      return;
    }
    cities.forEach(function(city) {
      const opt = document.createElement('option');
      opt.value = String(city.id || '');
      opt.dataset.country = city.country_code || '';
      opt.dataset.label = city.label || city.city || '';
      opt.dataset.timezone = city.timezone || 'UTC';
      opt.textContent = city.city || city.label || '';
      weatherCitySelect.appendChild(opt);
    });
    if (previous && Array.prototype.some.call(weatherCitySelect.options, function(opt) { return opt.value === previous; })) {
      weatherCitySelect.value = previous;
    } else {
      weatherCitySelect.selectedIndex = 0;
    }
    syncWeatherCityOptions();
  }

  function fetchWeatherCities(query) {
    if (!weatherCountrySelect || !weatherCitySelect || !weatherCityUrl) {
      syncWeatherCityOptions();
      return;
    }
    const country = (weatherCountrySelect.value || '').toUpperCase();
    const q = (query || '').trim();
    const token = ++weatherCityFetchToken;
    const url = weatherCityUrl + '?country_code=' + encodeURIComponent(country) + '&q=' + encodeURIComponent(q) + '&limit=220';
    fetch(url, { credentials: 'same-origin' })
      .then(function(resp) { return resp.ok ? resp.json() : null; })
      .then(function(data) {
        if (!data || token !== weatherCityFetchToken) return;
        renderWeatherCities(data.cities || []);
      })
      .catch(function() {
        if (token === weatherCityFetchToken) syncWeatherCityOptions();
      });
  }

  if (weatherCountrySelect && weatherCitySelect) {
    weatherCountrySelect.addEventListener('change', function() {
      fetchWeatherCities(weatherCitySearch ? weatherCitySearch.value : '');
      formDirty = true;
    });
    weatherCitySelect.addEventListener('change', function() {
      syncWeatherCityOptions();
      formDirty = true;
    });
    if (weatherCitySearch) {
      weatherCitySearch.addEventListener('input', function() {
        clearTimeout(weatherCityDebounce);
        weatherCityDebounce = setTimeout(function() {
          fetchWeatherCities(weatherCitySearch.value || '');
        }, 220);
      });
    }
    fetchWeatherCities(weatherCitySearch ? weatherCitySearch.value : '');
  }

  function updateStatusBadges() {
    if (!form) return;
    form.querySelectorAll('.feature-toggle-row').forEach(function(row) {
      const cb = row.querySelector('.feature-checkbox');
      const badge = row.querySelector('.status-badge');
      if (cb && badge) {
        badge.textContent = cb.checked ? 'On' : 'Off';
        badge.classList.toggle('bg-success', cb.checked);
        badge.classList.toggle('bg-secondary', !cb.checked);
      }
    });
  }

  if (form) {
    form.querySelectorAll('.feature-checkbox').forEach(function(cb) {
      cb.addEventListener('change', function() {
        updateStatusBadges();
        formDirty = true;
      });
    });
  }

  if (form) {
    form.querySelectorAll('.enable-all-cat').forEach(function(btn) {
      btn.addEventListener('click', function() {
        const cat = this.dataset.cat;
        form.querySelectorAll('.feature-checkbox[data-cat="' + cat + '"]').forEach(function(c) { c.checked = true; });
        updateStatusBadges();
        formDirty = true;
      });
    });
    form.querySelectorAll('.disable-all-cat').forEach(function(btn) {
      btn.addEventListener('click', function() {
        const cat = this.dataset.cat;
        form.querySelectorAll('.feature-checkbox[data-cat="' + cat + '"]').forEach(function(c) { c.checked = false; });
        updateStatusBadges();
        formDirty = true;
      });
    });
  }

  document.querySelectorAll('.preset-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      const presetId = this.dataset.preset;
      const presets = (window.__RMC_PAGE_DATA__["siteconfig__feature_control_panel_content-1"]||{})["var_bulk_presets_json_safe"];
      const preset = presets[presetId];
      if (!preset || !confirm('Apply preset "' + preset.label + '"? This will update toggles; click Save to apply.')) return;
      const setOn = preset.set_on || [];
      const setOff = preset.set_off || [];
      if (form) {
        form.querySelectorAll('.feature-checkbox').forEach(function(cb) {
          const name = cb.name.replace('feature_', '');
          if (setOn.indexOf(name) >= 0) cb.checked = true;
          else if (setOff.indexOf(name) >= 0) cb.checked = false;
        });
      }
      updateStatusBadges();
      formDirty = true;
    });
  });

  // v2.63 Wave A1: capability families segmented tabs. The 3-col grid was
  // dumping all ~9 categories at once (~2500px). Show one at a time;
  // search bypasses the tab to surface matches across all categories.
  const catTabBar = document.querySelector('[data-feature-cat-tabs="1"]');
  const catTabs = catTabBar ? Array.from(catTabBar.querySelectorAll('.feature-cat-tab')) : [];
  let activeCatId = catTabs.length ? (catTabs[0].dataset.cat || '') : '';
  let isSearchActive = false;

  function applyCategoryVisibility() {
    if (isSearchActive) {
      // Search active: ignore tab selection, show every category that has any matches.
      form.querySelectorAll('.feature-category').forEach(function(cat) {
        cat.classList.remove('d-none');
        cat.classList.remove('feature-category--hidden');
      });
      return;
    }
    if (activeCatId === '__all__') {
      form.querySelectorAll('.feature-category').forEach(function(cat) {
        cat.classList.remove('d-none');
        cat.classList.remove('feature-category--hidden');
      });
      return;
    }
    form.querySelectorAll('.feature-category').forEach(function(cat) {
      const matches = (cat.dataset.category || '') === activeCatId;
      cat.classList.toggle('d-none', !matches);
      cat.classList.toggle('feature-category--hidden', !matches);
    });
  }

  function setActiveCategory(catId) {
    activeCatId = catId || activeCatId;
    catTabs.forEach(function(tab) {
      const isActive = (tab.dataset.cat || '') === activeCatId;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    applyCategoryVisibility();
  }

  catTabs.forEach(function(tab) {
    tab.addEventListener('click', function() {
      setActiveCategory(tab.dataset.cat || activeCatId);
    });
  });

  // Initialise — first tab active, others hidden via the d-none we added in
  // the template. Calling apply once ensures the "All" pane is correctly
  // gated even when nothing was clicked yet.
  if (catTabs.length) {
    applyCategoryVisibility();
  }

  if (search && form) {
    search.addEventListener('input', function() {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(function() {
        const q = (search.value || '').toLowerCase().trim();
        isSearchActive = !!q;
        let anyVisible = false;
        form.querySelectorAll('.feature-category').forEach(function(cat) {
          let visibleCount = 0;
          cat.querySelectorAll('.feature-toggle-row').forEach(function(row) {
            const label = (row.dataset.label || '');
            const desc = (row.dataset.desc || '');
            const match = !q || label.indexOf(q) >= 0 || desc.indexOf(q) >= 0;
            row.classList.toggle('hidden-by-search', !match);
            if (match) visibleCount++;
          });
          cat.classList.toggle('hidden-by-search', visibleCount === 0);
          if (visibleCount > 0) anyVisible = true;
        });
        noResults.classList.toggle('d-none', !!q && !anyVisible);
        // Reapply tab visibility now that isSearchActive may have changed.
        applyCategoryVisibility();
      }, 200);
    });
  }

  let formDirty = false;
  if (form) {
    form.querySelectorAll('input, select').forEach(function(el) {
      el.addEventListener('change', function() { formDirty = true; });
    });
    form.addEventListener('submit', function() {
      formDirty = false;
      const btn = document.getElementById('btnSave');
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Saving...'; }
    });
  }
  window.addEventListener('beforeunload', function(e) {
    if (formDirty) e.preventDefault();
  });

  document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.key === 's') { e.preventDefault(); if (form) form.querySelector('[type="submit"]').click(); }
    if (e.key === 'Escape') { window.location.href = '(window.__RMC_PAGE_DATA__["siteconfig__feature_control_panel_content-1"]||{})["url_accounts_backend_dashboard"]'; }
  });

  const importFile = document.getElementById('importFile');
  const importTrigger = document.getElementById('importTrigger');
  if (importFile && importTrigger) {
    importTrigger.addEventListener('click', function() { importFile.click(); });
    importFile.addEventListener('change', function() {
      if (this.files && this.files[0] && confirm('Import will overwrite current feature settings and save immediately. Continue?')) {
        formDirty = false;
        if (form) form.submit();
      }
    });
  }

  function getFormState() {
    const state = {};
    if (form) form.querySelectorAll('.feature-checkbox').forEach(function(cb) {
      state[cb.name.replace('feature_', '')] = cb.checked;
    });
    return state;
  }

  function buildDiffHtml() {
    const next = getFormState();
    const changes = [];
    for (const k in currentState) {
      if (currentState[k] !== next[k]) {
        changes.push({ key: k, from: currentState[k], to: next[k] });
      }
    }
    if (changes.length === 0) return '<p class="text-muted mb-0">No changes to preview.</p>';
    let html = '<ul class="list-unstyled mb-0">';
    changes.forEach(function(c) {
      html += '<li class="py-1 border-bottom"><code>' + c.key + '</code>: ' + (c.from ? 'On' : 'Off') + ' → ' + (c.to ? 'On' : 'Off') + '</li>';
    });
    html += '</ul>';
    return html;
  }

  const diffModal = document.getElementById('diffModal');
  const diffModalBody = document.getElementById('diffModalBody');
  const diffModalSave = document.getElementById('diffModalSave');
  const btnPreviewDiff = document.getElementById('btnPreviewDiff');
  if (btnPreviewDiff && diffModalBody) {
    btnPreviewDiff.addEventListener('click', function() {
      diffModalBody.innerHTML = buildDiffHtml();
      if (typeof bootstrap !== 'undefined' && diffModal) {
        var modal = new bootstrap.Modal(diffModal);
        modal.show();
      }
    });
  }
  if (diffModalSave && diffModal) {
    diffModalSave.addEventListener('click', function() {
      if (typeof bootstrap !== 'undefined' && bootstrap.Modal.getInstance(diffModal)) {
        bootstrap.Modal.getInstance(diffModal).hide();
      }
      if (form) form.submit();
    });
  }

  if (form) {
    form.addEventListener('submit', function(e) {
      if (e.submitter && e.submitter.getAttribute('name') === 'action' && e.submitter.value === 'revert') return;
      let warn = false;
      criticalInputs.forEach(function(inp) { if (inp.checked === false) warn = true; });
      const depWarns = [];
      form.querySelectorAll('.feature-toggle-row[data-depends]').forEach(function(row) {
        const cb = row.querySelector('.feature-checkbox');
        if (!cb || !cb.checked) return;
        const deps = (row.dataset.depends || '').split(',').filter(Boolean);
        deps.forEach(function(dep) {
          const depEl = form.querySelector('[name="feature_' + dep.trim() + '"]');
          if (depEl && !depEl.checked) depWarns.push(cb.name.replace('feature_', '') + ' requires ' + dep.trim());
        });
      });
      if (depWarns.length && !confirm('Some enabled features depend on disabled ones: ' + depWarns.join('; ') + '. Continue?')) {
        e.preventDefault();
        return;
      }
      if (maintenanceInp && maintenanceInp.checked && !confirm('Enabling Maintenance Mode will redirect all users to a maintenance page. Continue?')) {
        e.preventDefault();
        return;
      }
      if (warn && !confirm('You are turning off critical features. Affected users may lose access. Continue?')) {
        e.preventDefault();
      }
    });
  }
})();
})();
