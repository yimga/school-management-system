/**
 * Color Palette Studio
 * Interactive UI for picking colors, generating harmonies, and applying to form fields.
 * Requires: color-harmony-engine.js, Pickr (already loaded via ColorInputWithPreview)
 */
(function () {
  'use strict';

  if (typeof colorHarmony === 'undefined') {
    console.warn('Color Palette Studio: colorHarmony not loaded');
    return;
  }

  function tok(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (_e) { return fallback; }
  }

  var studio = {};
  var state = {
    baseColor: tok('--school-primary', '#0d6efd'),
    harmonyType: 'complement',
    pickrInstance: null,
    selectedPreset: ''
  };

  function $(selector, parent) {
    return (parent || document).querySelector(selector);
  }

  function $$(selector, parent) {
    return Array.from((parent || document).querySelectorAll(selector));
  }

  function createElement(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        if (key === 'className') {
          el.className = attrs[key];
        } else if (key === 'style' && typeof attrs[key] === 'object') {
          Object.assign(el.style, attrs[key]);
        } else if (key.startsWith('on') && typeof attrs[key] === 'function') {
          el.addEventListener(key.slice(2).toLowerCase(), attrs[key]);
        } else {
          el.setAttribute(key, attrs[key]);
        }
      });
    }
    if (children) {
      if (typeof children === 'string') {
        el.textContent = children;
      } else if (Array.isArray(children)) {
        children.forEach(function (child) {
          if (child) el.appendChild(child);
        });
      } else {
        el.appendChild(children);
      }
    }
    return el;
  }

  var FIELD_LABELS = {
    primary_color: 'Primary',
    accent_color: 'Accent',
    header_bg_color: 'Header',
    footer_bg_color: 'Footer',
    success_color: 'Success',
    warning_color: 'Warning',
    danger_color: 'Danger'
  };

  function getPresetKeysSorted() {
    return colorHarmony.listPresets().sort(function (a, b) {
      var pa = colorHarmony.getPreset(a);
      var pb = colorHarmony.getPreset(b);
      var na = pa && pa.name ? pa.name : a;
      var nb = pb && pb.name ? pb.name : b;
      return na.localeCompare(nb);
    });
  }

  function getApplicableFields() {
    var order = ['primary_color', 'accent_color', 'header_bg_color', 'footer_bg_color', 'success_color', 'warning_color', 'danger_color'];
    var out = [];
    order.forEach(function (name) {
      var input = $('[name="' + name + '"]') || $('#id_' + name);
      if (input) {
        out.push({ name: name, label: FIELD_LABELS[name] || name });
      }
    });
    return out;
  }

  function renderStudioMeta(harmonyInfo) {
    var bestForEl = $('#cps-best-for');
    if (bestForEl && harmonyInfo) {
      bestForEl.textContent = 'Best for: ' + harmonyInfo.bestFor;
    }

    var descEl = $('#cps-harmony-description');
    if (descEl && harmonyInfo) {
      descEl.textContent = harmonyInfo.description;
    }
  }

  function renderSwatches(container) {
    if (!container) return;
    container.innerHTML = '';

    var colors = colorHarmony.generate(state.harmonyType, state.baseColor);
    var harmonyInfo = colorHarmony.HARMONIES[state.harmonyType];
    var applicableFields = getApplicableFields();
    if (applicableFields.length === 0) {
      applicableFields = [
        { name: 'primary_color', label: 'Primary' },
        { name: 'accent_color', label: 'Accent' }
      ];
    }

    colors.forEach(function (hex) {
      var actions = applicableFields.map(function (f) {
        return createElement('button', {
          type: 'button',
          className: 'cps-btn cps-btn-sm',
          onClick: function () { applyToField(f.name, hex); }
        }, f.label);
      });
      var swatch = createElement('div', { className: 'cps-swatch' }, [
        createElement('div', {
          className: 'cps-swatch-color',
          style: { backgroundColor: hex },
          title: 'Click to copy',
          onClick: function () { copyToClipboard(hex); }
        }, [
          createElement('span', { className: 'cps-swatch-hex-on-color' }, hex)
        ]),
        createElement('div', { className: 'cps-swatch-info' }, [
          createElement('span', { className: 'cps-swatch-hex' }, hex),
          createElement('div', { className: 'cps-swatch-actions' }, actions)
        ])
      ]);
      container.appendChild(swatch);
    });
    renderStudioMeta(harmonyInfo);
  }

  function shouldKeepThemePackAssignments() {
    var keep = $('#cps-keep-theme-pack');
    return !keep || !!keep.checked;
  }

  function clearThemePackAssignments() {
    if (shouldKeepThemePackAssignments()) return;
    if (window.ThemeStudio && typeof window.ThemeStudio.clearPack === 'function') {
      window.ThemeStudio.clearPack({ clearAdmin: true, clearSite: true });
      return;
    }
    var adminSelect = $('#id_admin_theme_pack');
    var siteSelect = $('#id_theme_pack');
    if (adminSelect) {
      adminSelect.value = '';
      adminSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (siteSelect) {
      siteSelect.value = '';
      siteSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function notifyStudioApplied(source, data) {
    if (typeof document.dispatchEvent !== 'function' || typeof CustomEvent !== 'function') return;
    document.dispatchEvent(new CustomEvent('theme-studio:applied', {
      detail: Object.assign({
        source: source || 'manual',
        mode: shouldKeepThemePackAssignments() ? 'keep-pack-selection' : 'clear-pack-selection'
      }, data || {})
    }));
  }

  function renderPresets(container) {
    if (!container) return;
    container.innerHTML = '';

    var presetKeys = getPresetKeysSorted();
    presetKeys.forEach(function (key) {
      var preset = colorHarmony.getPreset(key);
      if (!preset) return;

      var presetBtn = createElement('button', {
        type: 'button',
        className: 'cps-preset-btn' + (state.selectedPreset === key ? ' active' : ''),
        'data-preset-key': key,
        title: preset.bestFor,
        onClick: function () { applyPreset(key); }
      }, [
        createElement('span', { className: 'cps-preset-swatches' },
          preset.colors.map(function (c) {
            return createElement('span', {
              className: 'cps-preset-dot',
              style: { backgroundColor: c }
            });
          })
        ),
        createElement('span', { className: 'cps-preset-name' }, preset.name)
      ]);
      container.appendChild(presetBtn);
    });
  }

  function renderPresetSelect(selectEl) {
    if (!selectEl) return;
    var current = selectEl.value || '';
    while (selectEl.options.length > 1) {
      selectEl.remove(1);
    }

    getPresetKeysSorted().forEach(function (key) {
      var preset = colorHarmony.getPreset(key);
      if (!preset) return;
      var option = createElement('option', { value: key }, preset.name);
      selectEl.appendChild(option);
    });

    if (current) {
      selectEl.value = current;
    }
  }

  function setActivePresetUI() {
    var presetKey = state.selectedPreset || '';
    var preset = presetKey ? colorHarmony.getPreset(presetKey) : null;
    var keepPacks = shouldKeepThemePackAssignments();

    $$('.cps-preset-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-preset-key') === presetKey);
    });

    var presetSelect = $('#cps-preset-select');
    if (presetSelect) {
      presetSelect.value = presetKey;
    }

    var note = $('#cps-active-preset-note');
    if (!note) return;
    if (preset && preset.name) {
      note.textContent = 'Active preset: ' + preset.name + (keepPacks ? ' (ThemePack assignments preserved)' : ' (ThemePack assignments cleared on apply)');
    } else {
      note.textContent = keepPacks ? 'No preset selected. ThemePack assignments will be preserved.' : 'No preset selected. ThemePack assignments will be cleared on apply.';
    }
    note.classList.toggle('cps-active-preset-note-warning', !keepPacks);
  }

  function renderHarmonySelector(container) {
    if (!container) return;
    container.innerHTML = '';

    var harmonies = colorHarmony.listHarmonies();
    harmonies.forEach(function (key) {
      var h = colorHarmony.HARMONIES[key];
      var btn = createElement('button', {
        type: 'button',
        className: 'cps-harmony-btn' + (state.harmonyType === key ? ' active' : ''),
        'data-harmony': key,
        onClick: function () { selectHarmony(key); }
      }, h.name);
      container.appendChild(btn);
    });
  }

  function renderComboReference(container) {
    if (!container) return;
    container.innerHTML = '';

    var harmonies = colorHarmony.listHarmonies();
    harmonies.forEach(function (key) {
      var harmony = colorHarmony.HARMONIES[key];
      if (!harmony) return;
      var colors = colorHarmony.generate(key, state.baseColor).slice(0, 5);

      var swatches = createElement('div', { className: 'cps-combo-swatches' },
        colors.map(function (hex) {
          return createElement('button', {
            type: 'button',
            className: 'cps-combo-swatch',
            style: { backgroundColor: hex },
            title: 'Copy ' + hex,
            onClick: function (event) {
              event.stopPropagation();
              copyToClipboard(hex);
            }
          }, [
            createElement('span', { className: 'cps-combo-swatch-label' }, hex)
          ]);
        })
      );

      var card = createElement('div', {
        className: 'cps-combo-card' + (state.harmonyType === key ? ' active' : ''),
        role: 'button',
        tabIndex: 0,
        onClick: function () { selectHarmony(key); },
        onKeydown: function (event) {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            selectHarmony(key);
          }
        }
      }, [
        createElement('div', { className: 'cps-combo-head' }, [
          createElement('span', { className: 'cps-combo-name' }, harmony.name),
          createElement('button', {
            type: 'button',
            className: 'cps-btn cps-btn-sm cps-combo-use',
            onClick: function (event) {
              event.stopPropagation();
              selectHarmony(key);
            }
          }, 'Use')
        ]),
        createElement('p', { className: 'cps-combo-desc' }, harmony.description),
        swatches,
        createElement('p', { className: 'cps-combo-best' }, 'Best for: ' + harmony.bestFor)
      ]);

      container.appendChild(card);
    });
  }

  function refreshPaletteViews() {
    renderSwatches($('#cps-swatches'));
    renderComboReference($('#cps-combo-reference'));
  }

  function selectHarmony(harmonyType) {
    state.harmonyType = harmonyType;

    $$('.cps-harmony-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.harmony === harmonyType);
    });

    refreshPaletteViews();
  }

  function applyPreset(presetKey) {
    var preset = colorHarmony.getPreset(presetKey);
    if (!preset || !preset.colors.length) return;
    state.selectedPreset = presetKey;

    state.baseColor = colorHarmony.normalizeHex(preset.colors[0]);

    var baseInput = $('#cps-base-color-input');
    if (baseInput) {
      baseInput.value = state.baseColor;
    }
    if (state.pickrInstance) {
      state.pickrInstance.setColor(state.baseColor);
    }

    var baseSwatch = $('#cps-base-swatch');
    if (baseSwatch) {
      baseSwatch.style.backgroundColor = state.baseColor;
    }

    var presetSelect = $('#cps-preset-select');
    if (presetSelect) {
      presetSelect.value = presetKey;
    }
    setActivePresetUI();

    applyColorsToForm(preset.colors, colorHarmony.getPresetFieldMap(presetKey));
    clearThemePackAssignments();
    notifyStudioApplied('preset', {
      presetKey: presetKey,
      presetName: preset.name || presetKey
    });
    refreshPaletteViews();
    showToast('Applied preset: ' + (preset.name || presetKey));
  }

  function applyToField(fieldName, hex, options) {
    options = options || {};
    hex = colorHarmony.normalizeHex(hex);

    if (window.ThemeStudio && typeof window.ThemeStudio.setField === 'function') {
      if (window.ThemeStudio.setField(fieldName, hex)) {
        if (!options.silent) {
          showToast('Applied ' + hex + ' to ' + fieldName.replace(/_/g, ' '));
        }
        return;
      }
    }

    var input = $('[name="' + fieldName + '"]');
    if (!input) {
      input = $('#id_' + fieldName);
    }
    if (!input) {
      console.warn('Color Palette Studio: field not found:', fieldName);
      return;
    }

    input.value = hex;

    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.dispatchEvent(new Event('input', { bubbles: true }));

    var wrapper = input.closest('.color-input-with-preview');
    if (wrapper) {
      var trigger = wrapper.querySelector('.color-pickr-trigger');
      if (trigger) {
        trigger.style.backgroundColor = hex;
      }
    }

    if (!options.silent) {
      showToast('Applied ' + hex + ' to ' + fieldName.replace(/_/g, ' '));
    }
  }

  function fieldExists(fieldName) {
    return Boolean($('[name="' + fieldName + '"]') || $('#id_' + fieldName));
  }

  function colorAt(colors, index) {
    if (!colors || !colors.length) return '';
    if (colors[index]) return colors[index];
    if (colors.length > 1) return colors[colors.length - 1];
    return colors[0];
  }

  function applyColorsToForm(colors, fieldMap) {
    if (!colors || !colors.length) return;

    if (fieldMap && typeof fieldMap === 'object') {
      Object.keys(fieldMap).forEach(function (fieldName) {
        if (!fieldExists(fieldName)) return;
        var mapped = fieldMap[fieldName];
        if (mapped) applyToField(fieldName, mapped, { silent: true });
      });
      return;
    }

    var mapping = [
      { field: 'primary_color', index: 0 },
      { field: 'accent_color', index: 1 },
      { field: 'header_bg_color', index: 0 },
      { field: 'footer_bg_color', index: 2 },
      { field: 'success_color', index: 3 },
      { field: 'warning_color', index: 4 },
      { field: 'danger_color', index: 5 }
    ];

    mapping.forEach(function (entry) {
      if (!fieldExists(entry.field)) return;
      var color = colorAt(colors, entry.index);
      if (color) applyToField(entry.field, color, { silent: true });
    });
  }

  function applyPalette() {
    var colors = colorHarmony.generate(state.harmonyType, state.baseColor);
    state.selectedPreset = '';
    setActivePresetUI();
    applyColorsToForm(colors, colorHarmony.buildFieldMapFromColors(colors));
    clearThemePackAssignments();
    notifyStudioApplied('harmony', {
      harmonyType: state.harmonyType,
      baseColor: state.baseColor
    });
    showToast('Applied palette to form');
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        showToast('Copied: ' + text);
      }).catch(function () {
        copyToClipboardFallback(text);
      });
    } else {
      copyToClipboardFallback(text);
    }
  }

  function copyToClipboardFallback(text) {
    var textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    showToast('Copied: ' + text);
  }

  function showToast(message) {
    var existing = $('#cps-toast');
    if (existing) existing.remove();

    var toast = createElement('div', {
      id: 'cps-toast',
      className: 'cps-toast'
    }, message);

    document.body.appendChild(toast);

    setTimeout(function () {
      toast.classList.add('cps-toast-visible');
    }, 10);

    setTimeout(function () {
      toast.classList.remove('cps-toast-visible');
      setTimeout(function () {
        toast.remove();
      }, 300);
    }, 2000);
  }

  function initBasePicker() {
    var trigger = $('#cps-base-swatch');
    var input = $('#cps-base-color-input');
    if (!trigger || typeof Pickr === 'undefined') return;

    state.pickrInstance = Pickr.create({
      el: trigger,
      theme: 'classic',
      default: state.baseColor,
      useAsButton: true,
      defaultRepresentation: 'HEX',
      lockOpacity: true,
      components: {
        preview: true,
        opacity: false,
        hue: true,
        interaction: {
          hex: true,
          rgba: false,
          hsla: false,
          input: true,
          clear: false,
          save: true
        }
      }
    });

    state.pickrInstance.on('change', function (color) {
      if (!color) return;
      var hex = '#' + color.toHEXA().slice(0, 3).map(function (n) {
        var x = typeof n === 'number' ? Math.round(n) : parseInt(n, 10);
        var s = x.toString(16);
        return s.length === 1 ? '0' + s : s;
      }).join('');
      hex = colorHarmony.normalizeHex(hex);
      state.baseColor = hex;
      if (input) input.value = hex;
      trigger.style.backgroundColor = hex;
      refreshPaletteViews();
    });

    state.pickrInstance.on('save', function (color) {
      state.pickrInstance.hide();
    });

    // Sync input changes back to picker
    if (input) {
      input.addEventListener('change', function () {
        var hex = colorHarmony.normalizeHex(input.value);
        state.baseColor = hex;
        trigger.style.backgroundColor = hex;
        if (state.pickrInstance) {
          state.pickrInstance.setColor(hex);
        }
        refreshPaletteViews();
      });
    }
  }

  function initCollapse() {
    var header = $('#cps-header');
    var body = $('#cps-body');
    var toggle = $('#cps-toggle-icon');
    var storageKey = 'themeStudio.colorPalette.open';
    if (!header || !body) return;
    header.setAttribute('role', 'button');
    header.setAttribute('tabindex', '0');

    function setOpen(open) {
      body.style.display = open ? 'block' : 'none';
      header.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (toggle) {
        toggle.textContent = open ? 'expand_less' : 'expand_more';
      }
      try {
        window.localStorage.setItem(storageKey, open ? '1' : '0');
      } catch (error) {
        // Ignore storage errors (private mode / blocked storage).
      }
    }

    function readStoredOpenState() {
      try {
        var stored = window.localStorage.getItem(storageKey);
        if (stored === '1') return true;
        if (stored === '0') return false;
      } catch (error) {
        // Ignore storage errors and use default.
      }
      return false;
    }

    header.addEventListener('click', function () {
      var isOpen = body.style.display !== 'none';
      setOpen(!isOpen);
    });

    header.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        var isOpen = body.style.display !== 'none';
        setOpen(!isOpen);
      }
    });

    setOpen(readStoredOpenState());
  }

  function init() {
    var container = $('#color-palette-studio');
    if (!container) return;

    var primaryInput = $('[name="primary_color"]') || $('#id_primary_color');
    if (primaryInput && primaryInput.value) {
      state.baseColor = colorHarmony.normalizeHex(primaryInput.value);
    }

    var baseSwatch = $('#cps-base-swatch');
    var baseInput = $('#cps-base-color-input');
    if (baseSwatch) baseSwatch.style.backgroundColor = state.baseColor;
    if (baseInput) baseInput.value = state.baseColor;

    renderPresets($('#cps-presets'));
    renderPresetSelect($('#cps-preset-select'));
    renderHarmonySelector($('#cps-harmonies'));
    setActivePresetUI();
    refreshPaletteViews();

    initBasePicker();
    initCollapse();

    var applyPaletteBtn = $('#cps-apply-palette');
    if (applyPaletteBtn) {
      applyPaletteBtn.addEventListener('click', applyPalette);
    }

    var presetSelect = $('#cps-preset-select');
    if (presetSelect) {
      presetSelect.addEventListener('change', function () {
        if (!this.value) {
          state.selectedPreset = '';
          setActivePresetUI();
          return;
        }
        applyPreset(this.value);
      });
    }

    var keepPackToggle = $('#cps-keep-theme-pack');
    if (keepPackToggle) {
      keepPackToggle.addEventListener('change', setActivePresetUI);
    }

    document.addEventListener('theme-pack-selected', function () {
      if (!state.selectedPreset) return;
      state.selectedPreset = '';
      setActivePresetUI();
    });

    console.log('Color Palette Studio initialized');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  studio.init = init;
  studio.applyToField = applyToField;
  studio.applyPreset = applyPreset;
  studio.selectHarmony = selectHarmony;
  window.colorPaletteStudio = studio;

})();
