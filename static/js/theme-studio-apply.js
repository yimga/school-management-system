(function (window, document) {
  'use strict';

  function $(selector, parent) {
    return (parent || document).querySelector(selector);
  }

  function normalizeHex(value) {
    if (!value || typeof value !== 'string') return '';
    var v = value.trim();
    if (!v) return '';
    if (v.charAt(0) !== '#') v = '#' + v;
    return v;
  }

  function findField(fieldName) {
    return $("[name='" + fieldName + "']") || $("#id_" + fieldName);
  }

  function setField(fieldName, value) {
    var field = findField(fieldName);
    if (!field || !value) return false;

    var normalized = normalizeHex(value);
    field.value = normalized;
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));

    var wrapper = field.closest('.color-input-with-preview');
    if (wrapper) {
      var trigger = wrapper.querySelector('.color-pickr-trigger');
      if (trigger) trigger.style.backgroundColor = normalized;
    }
    return true;
  }

  function setPack(packId) {
    var select = document.getElementById('id_admin_theme_pack');
    if (!select || !packId) return false;
    select.value = String(packId);
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }

  function buildTokenMap(dataset) {
    if (!dataset) return [];
    var primary = dataset.primary || dataset.packPrimary || '';
    var accent = dataset.accent || dataset.packAccent || '';
    var background = dataset.background || dataset.packBackground || dataset.dashboardBg || '';
    var header = dataset.headerBg || primary;
    var footer = dataset.footerBg || dataset.dashboardBg || background;

    return [
      ['primary_color', primary],
      ['accent_color', accent],
      ['background_color', background],
      ['header_bg_color', header],
      ['footer_bg_color', footer],
      ['success_color', dataset.success || ''],
      ['warning_color', dataset.warning || ''],
      ['danger_color', dataset.danger || '']
    ];
  }

  function applyFromDataset(dataset, options) {
    options = options || {};
    var applied = [];
    var tokenMap = buildTokenMap(dataset);

    tokenMap.forEach(function (entry) {
      var fieldName = entry[0];
      var value = entry[1];
      if (setField(fieldName, value)) {
        applied.push(fieldName);
      }
    });

    if (options.setPack !== false && dataset && dataset.packId) {
      setPack(dataset.packId);
    }

    return applied;
  }

  window.ThemeStudio = window.ThemeStudio || {};
  window.ThemeStudio.findField = findField;
  window.ThemeStudio.setField = setField;
  window.ThemeStudio.setPack = setPack;
  window.ThemeStudio.applyFromDataset = applyFromDataset;
})(window, document);
