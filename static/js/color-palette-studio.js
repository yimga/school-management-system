/**
 * Color Palette Studio
 * Interactive UI for picking colors, generating harmonies, and applying to form fields.
 * Requires: color-harmony-engine.js, Pickr (already loaded via ColorInputWithPreview)
 */
(function () {
  'use strict';

  // Wait for colorHarmony to be available
  if (typeof colorHarmony === 'undefined') {
    console.warn('Color Palette Studio: colorHarmony not loaded');
    return;
  }

  var studio = {};
  var state = {
    baseColor: '#0d6efd',
    harmonyType: 'complement',
    pickrInstance: null
  };

  // ============================================================
  // DOM Helpers
  // ============================================================

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

  // Field names and labels: Studio can apply to any that exist on the form (Site Settings has more than Theme Pack / Report Card Style).
  var FIELD_LABELS = {
    primary_color: 'Primary',
    accent_color: 'Accent',
    background_color: 'Background',
    header_bg_color: 'Header',
    footer_bg_color: 'Footer',
    success_color: 'Success',
    warning_color: 'Warning',
    danger_color: 'Danger'
  };

  function getApplicableFields() {
    var order = ['primary_color', 'accent_color', 'background_color', 'header_bg_color', 'footer_bg_color', 'success_color', 'warning_color', 'danger_color'];
    var out = [];
    order.forEach(function (name) {
      var input = $('[name="' + name + '"]') || $('#id_' + name);
      if (input) {
        out.push({ name: name, label: FIELD_LABELS[name] || name });
      }
    });
    return out;
  }

  // ============================================================
  // Render Functions
  // ============================================================

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

    colors.forEach(function (hex, index) {
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
        }),
        createElement('div', { className: 'cps-swatch-info' }, [
          createElement('span', { className: 'cps-swatch-hex' }, hex),
          createElement('div', { className: 'cps-swatch-actions' }, actions)
        ])
      ]);
      container.appendChild(swatch);
    });

    // Best for text
    var bestForEl = $('#cps-best-for');
    if (bestForEl && harmonyInfo) {
      bestForEl.textContent = 'Best for: ' + harmonyInfo.bestFor;
    }

    // Description
    var descEl = $('#cps-harmony-description');
    if (descEl && harmonyInfo) {
      descEl.textContent = harmonyInfo.description;
    }
  }

  function renderPresets(container) {
    if (!container) return;
    container.innerHTML = '';

    var presetKeys = colorHarmony.listPresets();
    presetKeys.forEach(function (key) {
      var preset = colorHarmony.getPreset(key);
      if (!preset) return;

      var presetBtn = createElement('button', {
        type: 'button',
        className: 'cps-preset-btn',
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

  // ============================================================
  // Actions
  // ============================================================

  function selectHarmony(harmonyType) {
    state.harmonyType = harmonyType;

    // Update active button
    $$('.cps-harmony-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.harmony === harmonyType);
    });

    renderSwatches($('#cps-swatches'));
  }

  function applyPreset(presetKey) {
    var preset = colorHarmony.getPreset(presetKey);
    if (!preset || !preset.colors.length) return;

    // Apply first color as base
    state.baseColor = colorHarmony.normalizeHex(preset.colors[0]);

    // Update base color input and picker
    var baseInput = $('#cps-base-color-input');
    if (baseInput) {
      baseInput.value = state.baseColor;
    }
    if (state.pickrInstance) {
      state.pickrInstance.setColor(state.baseColor);
    }

    // Update base swatch
    var baseSwatch = $('#cps-base-swatch');
    if (baseSwatch) {
      baseSwatch.style.backgroundColor = state.baseColor;
    }

    applyColorsToForm(preset.colors);

    renderSwatches($('#cps-swatches'));
  }

  function applyToField(fieldName, hex, options) {
    options = options || {};
    hex = colorHarmony.normalizeHex(hex);

    // Try to find the field by name
    var input = $('[name="' + fieldName + '"]');
    if (!input) {
      // Try with id
      input = $('#id_' + fieldName);
    }
    if (!input) {
      console.warn('Color Palette Studio: field not found:', fieldName);
      return;
    }

    input.value = hex;

    // Dispatch change event for Pickr sync
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.dispatchEvent(new Event('input', { bubbles: true }));

    // Update the adjacent swatch if it's a ColorInputWithPreview
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

  function applyColorsToForm(colors) {
    if (!colors || !colors.length) return;

    var mapping = [
      { field: 'primary_color', index: 0 },
      { field: 'accent_color', index: 1 },
      { field: 'background_color', index: 2 },
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
    applyColorsToForm(colors);
    showToast('Applied palette to form');
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        showToast('Copied: ' + text);
      });
    } else {
      // Fallback
      var textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      showToast('Copied: ' + text);
    }
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

  // ============================================================
  // Base Color Picker
  // ============================================================

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
      renderSwatches($('#cps-swatches'));
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
        renderSwatches($('#cps-swatches'));
      });
    }
  }

  // ============================================================
  // Collapse Toggle
  // ============================================================

  function initCollapse() {
    var header = $('#cps-header');
    var body = $('#cps-body');
    var toggle = $('#cps-toggle-icon');
    if (!header || !body) return;

    header.addEventListener('click', function () {
      var isOpen = body.style.display !== 'none';
      body.style.display = isOpen ? 'none' : 'block';
      if (toggle) {
        toggle.textContent = isOpen ? 'expand_more' : 'expand_less';
      }
    });
  }

  // ============================================================
  // Initialize
  // ============================================================

  function init() {
    var container = $('#color-palette-studio');
    if (!container) return;

    // Get initial color from primary_color field if available
    var primaryInput = $('[name="primary_color"]') || $('#id_primary_color');
    if (primaryInput && primaryInput.value) {
      state.baseColor = colorHarmony.normalizeHex(primaryInput.value);
    }

    // Set initial base color display
    var baseSwatch = $('#cps-base-swatch');
    var baseInput = $('#cps-base-color-input');
    if (baseSwatch) baseSwatch.style.backgroundColor = state.baseColor;
    if (baseInput) baseInput.value = state.baseColor;

    // Render components
    renderPresets($('#cps-presets'));
    renderHarmonySelector($('#cps-harmonies'));
    renderSwatches($('#cps-swatches'));

    // Initialize picker
    initBasePicker();

    // Initialize collapse
    initCollapse();

    // Apply palette button
    var applyPaletteBtn = $('#cps-apply-palette');
    if (applyPaletteBtn) {
      applyPaletteBtn.addEventListener('click', applyPalette);
    }

    console.log('Color Palette Studio initialized');
  }

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Export for manual init if needed
  studio.init = init;
  studio.applyToField = applyToField;
  studio.applyPreset = applyPreset;
  studio.selectHarmony = selectHarmony;
  window.colorPaletteStudio = studio;

})();
