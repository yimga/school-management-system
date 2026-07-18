(function(){
  var pageDataEl=document.getElementById("page-data-siteconfig__partials__theme_colors_page_body-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var colorFieldNames = ['primary_color', 'accent_color', 'header_bg_color', 'footer_bg_color', 'success_color', 'warning_color', 'danger_color'];
  var contrastBadge = null;
  var contrastTargets = {};
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

  function loadContrastTargets() {
    var el = document.getElementById('theme-contrast-targets');
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || '{}');
    } catch (_e) {
      return {};
    }
  }

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function surfaceRemediatePanel(message, show) {
    var panel = document.getElementById('theme-contrast-remediate-panel');
    if (!panel) return;
    panel.textContent = message || '';
    panel.classList.toggle('d-none', !show);
  }

  function updateContrastBadge(dirty) {
    if (!contrastBadge || !window.ContrastGuard || !window.ContrastGuard.buildThemeContrastReport) return;
    var values = {};
    colorFieldNames.forEach(function(name) {
      values[name] = readFieldValue(name);
    });
    var report = window.ContrastGuard.buildThemeContrastReport(values, contrastTargets);
    var pageData = window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {};
    var ok = report.status === 'ok';
    contrastBadge.textContent = ok
      ? (pageData.trans_contrast_pass || 'Contrast safety: pass')
      : (pageData.trans_contrast_needs_attention || 'Contrast safety: needs attention');
    contrastBadge.dataset.status = report.status;
    contrastBadge.classList.toggle('text-bg-success-subtle', ok);
    contrastBadge.classList.toggle('text-bg-warning', !ok);
    var remediateBtn = document.getElementById('theme-contrast-auto-remediate');
    if (remediateBtn) {
      remediateBtn.classList.toggle('d-none', ok || !(report.failures && report.failures.length));
    }
    if (ok) {
      surfaceRemediatePanel('', false);
    } else if (report.failures && report.failures.length) {
      var lines = report.failures.map(function(f) {
        return (f.field || '') + ': ' + (f.ratio ? f.ratio.toFixed(1) : '?') + ':1 (need ' + (f.min_ratio || 4.5) + ':1)';
      });
      surfaceRemediatePanel(lines.join(' · '), true);
    }
    if (activeSource) {
      activeSource.textContent = dirty
        ? (pageData.trans_source_draft_values || 'Source: draft values')
        : (pageData.trans_source_saved_values || 'Source: saved values');
    }
    return report;
  }

  function applyBrandRemediations() {
    var pageData = window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {};
    var url = pageData.url_brand_contrast_remediate;
    if (!url) return Promise.resolve();
    var surface = readFieldValue('background_color') || '#ffffff';
    var report = updateContrastBadge(true);
    if (!report || !report.failures || !report.failures.length) return Promise.resolve();
    var remediateBtn = document.getElementById('theme-contrast-auto-remediate');
    if (remediateBtn) remediateBtn.disabled = true;
    var chain = Promise.resolve();
    report.failures.forEach(function(failure) {
      var field = failure.field;
      var brand = readFieldValue(field);
      if (!brand) return;
      chain = chain.then(function() {
        return fetch(url, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-CSRFToken': csrfToken()
          },
          body: JSON.stringify({
            brand_hex: brand,
            background_hex: surface,
            min_ratio: 7.0
          })
        }).then(function(res) {
          return res.json();
        }).then(function(body) {
          if (body && body.remediated_hex && body.adjusted) {
            var input = fieldByName(field);
            if (input) {
              input.value = body.remediated_hex;
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.dispatchEvent(new Event('change', { bubbles: true }));
            }
          }
        });
      });
    });
    return chain.finally(function() {
      if (remediateBtn) remediateBtn.disabled = false;
      updateDraftState();
      if (typeof window.showToast === 'function') {
        window.showToast('Brand colors shifted for AAA contrast', 'success', 3000);
      }
    });
  }

  function updateDraftState() {
    if (!draftBadge) return;
    var dirty = trackedFieldNames.some(function(name) {
      return readFieldValue(name) !== (savedSnapshot[name] || '');
    });
    draftBadge.textContent = dirty ? ((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_draft_changes_pending"]) : ((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_saved_state"]);
    draftBadge.classList.toggle('text-bg-warning', dirty);
    draftBadge.classList.toggle('text-bg-warning-subtle', dirty);
    draftBadge.classList.toggle('text-bg-success-subtle', !dirty);
    updateContrastBadge(dirty);
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
    contrastBadge = document.getElementById('theme-contrast-status-badge');
    activeSource = document.getElementById('theme-active-source');
    contrastTargets = loadContrastTargets();

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
      form.addEventListener('change', function(e) {
        updateDraftState();
        writeActiveLabel('theme-active-site-pack', 'id_theme_pack');
        writeActiveLabel('theme-active-admin-pack', 'id_admin_theme_pack');
        updatePackParityNote();
        // Any form edit invalidates prior preview evidence (except the confirm checkbox itself).
        var t = e && e.target;
        if (t && t.id === 'theme-confirm-publish') return;
        form.setAttribute('data-rmc-preview-rendered', '0');
        var previewConfirmedField = document.getElementById('theme-preview-confirmed');
        if (previewConfirmedField) previewConfirmedField.value = '0';
        var confirmCheck = document.getElementById('theme-confirm-publish');
        if (confirmCheck) {
          confirmCheck.checked = false;
          confirmCheck.disabled = true;
        }
        var status = document.getElementById('theme-preview-evidence-status');
        if (status) {
          status.textContent = ((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_preview_evidence_needed"]) || 'Open Live preview and verify before confirming.';
          status.classList.add('text-muted');
          status.classList.remove('text-success');
        }
      });
      form.addEventListener('submit', function() {
        setSource(((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_source_saving_current_form_values"]));
        var confirmCheck = document.getElementById('theme-confirm-publish');
        var previewConfirmedField = document.getElementById('theme-preview-confirmed');
        var evidenced = form.getAttribute('data-rmc-preview-rendered') === '1';
        if (confirmCheck && previewConfirmedField && confirmCheck.checked && evidenced) {
          previewConfirmedField.value = '1';
        } else if (previewConfirmedField) {
          previewConfirmedField.value = '0';
        }
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
    var previewRendered = false;
    var lastPreviewUrl = '';
    var pageData = function () {
      return window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {};
    };

    function setPreviewEvidence(ok, detail) {
      previewRendered = !!ok;
      if (form) form.setAttribute('data-rmc-preview-rendered', ok ? '1' : '0');
      var status = document.getElementById('theme-preview-evidence-status');
      if (status) {
        status.textContent = ok
          ? (pageData()["trans_preview_evidence_ok"] || 'Preview verified — you can confirm publish.')
          : (pageData()["trans_preview_evidence_needed"] || 'Open Live preview and verify before confirming.');
        status.classList.toggle('text-success', !!ok);
        status.classList.toggle('text-muted', !ok);
      }
      if (confirmCheck) {
        if (!ok) {
          confirmCheck.checked = false;
          confirmCheck.disabled = true;
          if (previewConfirmedField) previewConfirmedField.value = '0';
        } else {
          confirmCheck.disabled = false;
        }
      }
      var root = document.getElementById('theme-live-preview-contract');
      if (root) root.setAttribute('data-rmc-preview-evidence', ok ? '1' : '0');
      if (detail && typeof window.showToast === 'function' && ok) {
        /* toast handled by caller */
      }
    }

    function showFallbackPanel(url) {
      var panel = document.querySelector('#theme-live-preview-contract [data-rmc-preview-fallbacks]');
      var newTab = document.querySelector('#theme-live-preview-contract [data-rmc-preview-new-tab]');
      var frame = document.querySelector('#theme-live-preview-contract iframe[data-rmc-preview-frame]');
      if (panel) panel.hidden = false;
      if (newTab && url) {
        newTab.href = url;
        newTab.removeAttribute('aria-disabled');
      }
      if (frame && url) {
        frame.dataset.loaded = '0';
        frame.src = url;
        frame.addEventListener('load', function onLoad() {
          frame.dataset.loaded = '1';
          setPreviewEvidence(true);
          frame.removeEventListener('load', onLoad);
        });
      }
      var root = document.getElementById('theme-live-preview-contract');
      if (root) root.setAttribute('data-rmc-preview-state', 'fallback');
    }

    function openPreviewUrl(url) {
      if (!url) return false;
      lastPreviewUrl = url;
      var popup = null;
      try {
        popup = window.open(url, '_blank', 'noopener,noreferrer');
      } catch (e) {
        popup = null;
      }
      var blocked = !popup || popup.closed || typeof popup.closed === 'undefined';
      if (blocked) {
        showFallbackPanel(url);
        if (typeof window.showToast === 'function') {
          window.showToast(
            pageData()["trans_preview_popup_blocked"] || 'Popup blocked — use a fallback preview below.',
            'warning',
            4000
          );
        }
        return false;
      }
      // Popup opened: enable confirm after a short settle (user can see the tab).
      window.setTimeout(function () {
        try {
          if (popup && !popup.closed) setPreviewEvidence(true);
          else showFallbackPanel(url);
        } catch (e2) {
          // Cross-origin closed check may throw — treat open as evidence.
          setPreviewEvidence(true);
        }
      }, 400);
      return true;
    }

    if (confirmCheck && previewConfirmedField) {
      confirmCheck.disabled = true;
      confirmCheck.addEventListener('change', function() {
        if (confirmCheck.checked && !previewRendered) {
          confirmCheck.checked = false;
          previewConfirmedField.value = '0';
          if (typeof window.showToast === 'function') {
            window.showToast(
              pageData()["trans_preview_evidence_needed"] || 'Open Live preview and verify before confirming.',
              'warning',
              3500
            );
          }
          return;
        }
        previewConfirmedField.value = confirmCheck.checked && previewRendered ? '1' : '0';
      });
    }

    window.addEventListener('message', function (event) {
      if (!event || event.origin !== window.location.origin) return;
      var data = event.data;
      if (data === 'rmc-preview-loaded' || (data && data.type === 'rmc-preview-loaded')) {
        setPreviewEvidence(true);
      }
    });

    var fallbackRoot = document.getElementById('theme-live-preview-contract');
    if (fallbackRoot) {
      var modalBtn = fallbackRoot.querySelector('[data-rmc-preview-modal]');
      var popoutBtn = fallbackRoot.querySelector('[data-rmc-preview-popout]');
      var retryBtn = fallbackRoot.querySelector('[data-rmc-preview-retry]');
      var openBest = fallbackRoot.querySelector('[data-rmc-preview-open-best]');
      function openModalPreview(url) {
        var modal = document.getElementById('theme-live-preview-modal');
        var modalFrame = modal && modal.querySelector('[data-rmc-live-preview-modal-frame]');
        if (modalFrame && url) modalFrame.src = url;
        if (modal && window.bootstrap && window.bootstrap.Modal) {
          window.bootstrap.Modal.getOrCreateInstance(modal).show();
          setPreviewEvidence(true);
          return;
        }
        openPreviewUrl(url);
      }
      function wireOpen(el, mode) {
        if (!el) return;
        el.addEventListener('click', function () {
          var url = lastPreviewUrl || (el.getAttribute('href') && el.getAttribute('href') !== '#' ? el.getAttribute('href') : '');
          if (!url) return;
          if (mode === 'modal') openModalPreview(url);
          else if (mode === 'popout') {
            var w = window.open(url, 'rmc-theme-preview', 'popup,width=1280,height=900,noopener,noreferrer');
            if (!w) showFallbackPanel(url);
            else setPreviewEvidence(true);
          } else if (mode === 'retry') showFallbackPanel(url);
          else openPreviewUrl(url);
        });
      }
      wireOpen(modalBtn, 'modal');
      wireOpen(popoutBtn, 'popout');
      wireOpen(retryBtn, 'retry');
      wireOpen(openBest, 'best');
    }

    document.addEventListener('theme-pack-selected', function(event) {
      if (!event || !event.detail) return;
      var name = event.detail.packName || event.detail.packSlug || event.detail.packId || '';
      setSource(name ? ('(window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"]||{})["trans_source_selected_theme_pack"] ' + name) : ((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_source_selected_theme_pack_2"]));
      writeActiveLabel('theme-active-site-pack', 'id_theme_pack');
      writeActiveLabel('theme-active-admin-pack', 'id_admin_theme_pack');
      updatePackParityNote();
      updateDraftState();
      // Draft changed — require a fresh preview before confirm.
      setPreviewEvidence(false);
    });

    document.addEventListener('theme-studio:applied', function(event) {
      if (!event || !event.detail) return;
      if (event.detail.source === 'theme-pack') {
        setSource(((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_source_theme_pack_colors_applied_to_form"]));
      } else if (event.detail.source === 'preset') {
        setSource(((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_source_preset_palette_applied"]));
      } else if (event.detail.source === 'harmony') {
        setSource(((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_source_generated_harmony_applied"]));
      } else {
        setSource(((window.__RMC_PAGE_DATA__["siteconfig__partials__theme_colors_page_body-1"] || {})["trans_source_manual_edit"]));
      }
      updateDraftState();
      setPreviewEvidence(false);
    });

    var remediateBtn = document.getElementById('theme-contrast-auto-remediate');
    if (remediateBtn) {
      remediateBtn.addEventListener('click', function() {
        applyBrandRemediations();
      });
    }

    var previewBtn = document.getElementById('theme-colors-live-preview');
    if (previewBtn && form) {
      previewBtn.addEventListener('click', function() {
        var fd = new FormData(form);
        fd.append('preview_section', 'theme-experience');
        var keepEl = document.getElementById('theme-colors-preview-keep');
        if (keepEl && keepEl.checked) fd.append('preview_keep', '1');
        // Do NOT set preview_confirmed here — confirmation requires visual proof.
        if (previewConfirmedField) previewConfirmedField.value = '0';
        if (confirmCheck) {
          confirmCheck.checked = false;
          confirmCheck.disabled = true;
        }
        previewRendered = false;
        var csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
        var url = pageData()["url_siteconfig_preview_from_form"];
        fetch(url, { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrf ? csrf.value : '', 'Accept': 'application/json' }, credentials: 'same-origin' })
          .then(function(r) { return r.json().then(function(data) { return { ok: r.ok, data: data }; }); })
          .then(function(res) {
            if (!res.ok) {
              var msg = (res.data.errors && res.data.errors.length) ? res.data.errors.join(' ') : (pageData()["trans_preview_failed"]);
              if (typeof window.showToast === 'function') window.showToast(msg, 'error', 4000);
              return;
            }
            var redirectUrl = res.data && res.data.redirect_url;
            if (!redirectUrl) {
              if (typeof window.showToast === 'function') window.showToast(pageData()["trans_preview_failed"] || 'Preview failed', 'error', 4000);
              return;
            }
            var opened = openPreviewUrl(redirectUrl);
            if (opened && typeof window.showToast === 'function') {
              window.showToast(pageData()["trans_preview_opened_in_new_tab"] || 'Preview opened in new tab', 'success', 2000);
            }
            // Always also refresh inline mock so the on-page surface reflects draft colors.
            var inline = document.querySelector('.theme-preview-section');
            if (inline) inline.setAttribute('data-rmc-preview-activated', '1');
          })
          .catch(function() {
            if (typeof window.showToast === 'function') window.showToast(pageData()["trans_preview_failed_2"] || 'Preview failed', 'error', 3000);
          });
      });
    }

    // Form submit: only emit preview_confirmed when checkbox + evidence both hold.
    if (form && previewConfirmedField) {
      form.addEventListener('submit', function () {
        if (confirmCheck && confirmCheck.checked && previewRendered) {
          previewConfirmedField.value = '1';
        } else if (!(pageData()["skip_theme_publish_guard"] === '1')) {
          previewConfirmedField.value = '0';
        }
      });
    }

    setPreviewEvidence(false);

    // If publish guard is intentionally skipped, allow confirm without preview evidence.
    var skipGuard = document.getElementById('id_skip_theme_publish_guard');
    function syncSkipGuard() {
      if (skipGuard && skipGuard.checked) {
        if (confirmCheck) confirmCheck.disabled = false;
        if (form) form.setAttribute('data-rmc-preview-rendered', '1');
        previewRendered = true;
        var status = document.getElementById('theme-preview-evidence-status');
        if (status) {
          status.textContent = pageData()["trans_preview_evidence_ok"] || 'Preview verified — you can confirm publish.';
          status.classList.add('text-success');
          status.classList.remove('text-muted');
        }
      }
    }
    if (skipGuard) {
      skipGuard.addEventListener('change', syncSkipGuard);
      syncSkipGuard();
    }
  });
})();
})();
