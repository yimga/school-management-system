(function(){
  var pageDataEl=document.getElementById("page-data-siteconfig__partials__theme_colors_page_body-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var colorFieldNames = ['primary_color', 'accent_color', 'header_bg_color', 'footer_bg_color', 'success_color', 'warning_color', 'danger_color'];
  var trackedFieldNames = colorFieldNames.concat([
    'theme_pack',
    'admin_theme_pack',
    'teacher_theme_pack',
    'parent_theme_pack',
    'theme_brightness',
    'backend_console_theme',
    'use_dark_mode',
    'admin_use_site_primary',
    'secondary_font',
    'base_font_size',
    'use_secondary_font_for_headings',
    'default_dashboard_view',
    'default_refresh_rate',
    'default_term_report_style',
    'default_annual_report_style',
    'report_downloads_enabled',
    'skip_theme_publish_guard'
  ]);
  var savedSnapshot = {};
  var draftBadge = null;
  var activeSource = null;
  var form = null;

  function fieldByName(name) {
    return document.querySelector('#theme-colors-form [name="' + name + '"]');
  }

  function readFieldValue(name) {
    var input = fieldByName(name);
    if (!input) return '';
    if (input.type === 'checkbox') return input.checked ? '1' : '0';
    return input.value || '';
  }

  function writeActiveLabel(labelId, selectId) {
    var label = document.getElementById(labelId);
    var select = document.getElementById(selectId);
    if (!label || !select) return;
    var selectedText = '';
    if (select.options && select.selectedIndex >= 0 && select.options[select.selectedIndex]) {
      selectedText = select.options[select.selectedIndex].text || '';
    }
    label.textContent = selectedText || label.getAttribute('data-empty-label') || 'None selected';
  }

  function setSource(text) {
    if (!activeSource || !text) return;
    activeSource.textContent = text;
  }

  function updatePackParityNote() {
    var note = document.getElementById('theme-pack-parity-note');
    var siteField = document.getElementById('id_theme_pack');
    var adminField = document.getElementById('id_admin_theme_pack');
    if (!note || !siteField || !adminField) return;

    var sitePack = String(siteField.value || '');
    var adminPack = String(adminField.value || '');
    var unified = sitePack !== '' && sitePack === adminPack;
    note.textContent = unified
      ? (note.dataset.unifiedLabel || 'Unified pack active across site and admin.')
      : (note.dataset.splitLabel || 'Site and admin packs differ. Visual style may diverge.');
    note.classList.toggle('text-success', unified);
    note.classList.toggle('text-warning', !unified);
  }

  function updateDraftState() {
    if (!draftBadge) return;
    var dirty = trackedFieldNames.some(function(name) {
      return readFieldValue(name) !== (savedSnapshot[name] || '');
    });
    draftBadge.textContent = dirty ? '(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_draft_changes_pending"]' : '(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_saved_state"]';
    draftBadge.classList.toggle('text-bg-warning', dirty);
    draftBadge.classList.toggle('text-bg-warning-subtle', dirty);
    draftBadge.classList.toggle('text-bg-success-subtle', !dirty);
  }

  function snapshot() {
    trackedFieldNames.forEach(function(name) {
      savedSnapshot[name] = readFieldValue(name);
    });
  }

  function revert() {
    var reverted = 0;
    colorFieldNames.forEach(function(name) {
      if (savedSnapshot[name] === undefined) return;
      var input = fieldByName(name);
      if (input && input.value !== savedSnapshot[name]) {
        input.value = savedSnapshot[name];
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        reverted++;
      }
    });
    updateDraftState();
    if (reverted > 0 && typeof window.showToast === 'function') window.showToast('Colors reverted to saved values', 'success', 2500);
  }

  document.addEventListener('DOMContentLoaded', function() {
    form = document.getElementById('theme-colors-form');
    draftBadge = document.getElementById('theme-draft-status-badge');
    activeSource = document.getElementById('theme-active-source');

    function syncAdminPrimaryGuard() {
      var lockToggle = document.getElementById('id_admin_use_site_primary');
      var applySite = document.getElementById('theme-pack-apply-site');
      var guard = document.getElementById('admin-use-site-primary-guard');
      if (!lockToggle) return;

      var locked = !!lockToggle.checked;
      if (guard) guard.classList.toggle('d-none', !locked);

      if (applySite) {
        if (locked) {
          applySite.dataset.prevChecked = applySite.checked ? '1' : '0';
          applySite.checked = true;
          applySite.disabled = true;
          applySite.title = 'Locked while Admin use site primary is enabled.';
        } else {
          if (applySite.dataset.prevChecked !== undefined) {
            applySite.checked = applySite.dataset.prevChecked === '1';
            delete applySite.dataset.prevChecked;
          }
          applySite.disabled = false;
          applySite.title = '';
        }
      }
    }

    snapshot();
    syncAdminPrimaryGuard();
    writeActiveLabel('theme-active-site-pack', 'id_theme_pack');
    writeActiveLabel('theme-active-admin-pack', 'id_admin_theme_pack');
    updatePackParityNote();
    updateDraftState();

    var adminUseSitePrimary = document.getElementById('id_admin_use_site_primary');
    if (adminUseSitePrimary) {
      adminUseSitePrimary.addEventListener('change', syncAdminPrimaryGuard);
    }

    var btn = document.getElementById('theme-revert-to-saved');
    if (btn) btn.addEventListener('click', function() { revert(); });

    if (form) {
      form.addEventListener('input', updateDraftState);
      form.addEventListener('change', function() {
        updateDraftState();
        writeActiveLabel('theme-active-site-pack', 'id_theme_pack');
        writeActiveLabel('theme-active-admin-pack', 'id_admin_theme_pack');
        updatePackParityNote();
        var previewConfirmedField = document.getElementById('theme-preview-confirmed');
        if (previewConfirmedField) previewConfirmedField.value = '0';
        var confirmCheck = document.getElementById('theme-confirm-publish');
        if (confirmCheck && previewConfirmedField) previewConfirmedField.value = confirmCheck.checked ? '1' : '0';
      });
      form.addEventListener('submit', function() {
        setSource('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_source_saving_current_form_values"]');
        var confirmCheck = document.getElementById('theme-confirm-publish');
        var previewConfirmedField = document.getElementById('theme-preview-confirmed');
        if (confirmCheck && previewConfirmedField && confirmCheck.checked) previewConfirmedField.value = '1';
      });
    }

    var useSamePackBtn = document.getElementById('theme-use-same-pack');
    if (useSamePackBtn && form) {
      useSamePackBtn.addEventListener('click', function() {
        var siteSelect = document.getElementById('id_theme_pack');
        var adminSelect = document.getElementById('id_admin_theme_pack');
        if (siteSelect && adminSelect && siteSelect.value) {
          adminSelect.value = siteSelect.value;
          adminSelect.dispatchEvent(new Event('change', { bubbles: true }));
          writeActiveLabel('theme-active-admin-pack', 'id_admin_theme_pack');
          updatePackParityNote();
          updateDraftState();
        }
      });
    }

    var confirmCheck = document.getElementById('theme-confirm-publish');
    var previewConfirmedField = document.getElementById('theme-preview-confirmed');
    if (confirmCheck && previewConfirmedField) {
      confirmCheck.addEventListener('change', function() {
        previewConfirmedField.value = confirmCheck.checked ? '1' : '0';
      });
    }

    document.addEventListener('theme-pack-selected', function(event) {
      if (!event || !event.detail) return;
      var name = event.detail.packName || event.detail.packSlug || event.detail.packId || '';
      setSource(name ? ('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_source_selected_theme_pack"] ' + name) : '(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_source_selected_theme_pack_2"]');
      writeActiveLabel('theme-active-site-pack', 'id_theme_pack');
      writeActiveLabel('theme-active-admin-pack', 'id_admin_theme_pack');
      updatePackParityNote();
      updateDraftState();
    });

    document.addEventListener('theme-studio:applied', function(event) {
      if (!event || !event.detail) return;
      if (event.detail.source === 'theme-pack') {
        setSource('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_source_theme_pack_colors_applied_to_form"]');
      } else if (event.detail.source === 'preset') {
        setSource('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_source_preset_palette_applied"]');
      } else if (event.detail.source === 'harmony') {
        setSource('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_source_generated_harmony_applied"]');
      } else {
        setSource('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_source_manual_edit"]');
      }
      updateDraftState();
    });

    var previewBtn = document.getElementById('theme-colors-live-preview');
    if (previewBtn && form) {
      previewBtn.addEventListener('click', function() {
        var fd = new FormData(form);
        fd.append('preview_section', 'theme-experience');
        var keepEl = document.getElementById('theme-colors-preview-keep');
        if (keepEl && keepEl.checked) fd.append('preview_keep', '1');
        var previewConfirmedField = document.getElementById('theme-preview-confirmed');
        if (previewConfirmedField) previewConfirmedField.value = '1';
        var csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
        var url = '(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["url_siteconfig_preview_from_form"]';
        fetch(url, { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrf ? csrf.value : '', 'Accept': 'application/json' }, credentials: 'same-origin' })
          .then(function(r) { return r.json().then(function(data) { return { ok: r.ok, data: data }; }); })
          .then(function(res) {
            if (!res.ok) {
              var msg = (res.data.errors && res.data.errors.length) ? res.data.errors.join(' ') : '(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_preview_failed"]';
              if (typeof window.showToast === 'function') window.showToast(msg, 'error', 4000);
              return;
            }
            if (res.data.redirect_url) window.open(res.data.redirect_url, '_blank', 'noopener');
            if (typeof window.showToast === 'function') window.showToast('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_preview_opened_in_new_tab"]', 'success', 2000);
          })
          .catch(function() {
            if (typeof window.showToast === 'function') window.showToast('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_preview_failed_2"]', 'error', 3000);
          });
      });
    }
  });
})();
})();
