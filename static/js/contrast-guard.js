/**
 * Contrast Auto-Guard: pick text color for a background to meet WCAG 4.5:1.
 * Use for theme pack preview, dynamic badges, chips, and buttons.
 */
(function (root) {
  'use strict';

  /**
   * Relative luminance (0–1) from hex or rgb.
   * @param {string} hex - e.g. "#3b82f6" or "3b82f6"
   * @returns {number}
   */
  function luminanceFromHex(hex) {
    hex = hex.replace(/^#/, '');
    if (hex.length === 3) {
      hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    }
    var r = parseInt(hex.slice(0, 2), 16) / 255;
    var g = parseInt(hex.slice(2, 4), 16) / 255;
    var b = parseInt(hex.slice(4, 6), 16) / 255;
    r = r <= 0.03928 ? r / 12.92 : Math.pow((r + 0.055) / 1.055, 2.4);
    g = g <= 0.03928 ? g / 12.92 : Math.pow((g + 0.055) / 1.055, 2.4);
    b = b <= 0.03928 ? b / 12.92 : Math.pow((b + 0.055) / 1.055, 2.4);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  /**
   * Contrast ratio between two luminances.
   * @param {number} L1
   * @param {number} L2
   * @returns {number}
   */
  function contrastRatio(L1, L2) {
    var lighter = Math.max(L1, L2);
    var darker = Math.min(L1, L2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  /**
   * Return '#000000' or '#ffffff' for text on the given background to meet ~4.5:1.
   * @param {string} bgHex - background color hex
   * @returns {string}
   */
  function textColorForBackground(bgHex) {
    var Lbg = luminanceFromHex(bgHex);
    var Lblack = 0;
    var Lwhite = 1;
    var onBlack = contrastRatio(Lbg, Lblack);
    var onWhite = contrastRatio(Lbg, Lwhite);
    return onBlack >= 4.5 ? '#000000' : '#ffffff';
  }

  /**
   * Set a CSS custom property or element style for text color based on background.
   * @param {HTMLElement} el - element with background color
   * @param {string} prop - e.g. '--contrast-fg' or 'color'
   * @param {string} [bgHex] - optional; if not set, read from computed background
   */
  function applyContrastFg(el, prop, bgHex) {
    if (!el) return;
    var bg = bgHex || getComputedStyle(el).backgroundColor;
    var hex = rgbToHex(bg);
    if (!hex) return;
    var fg = textColorForBackground(hex);
    if (prop === 'color') {
      el.style.color = fg;
    } else {
      el.style.setProperty(prop, fg);
    }
  }

  function rgbToHex(rgb) {
    if (!rgb || rgb.indexOf('rgb') === -1) {
      return rgb && rgb.indexOf('#') === 0 ? rgb : null;
    }
    var m = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!m) return null;
    var r = ('0' + parseInt(m[1], 10).toString(16)).slice(-2);
    var g = ('0' + parseInt(m[2], 10).toString(16)).slice(-2);
    var b = ('0' + parseInt(m[3], 10).toString(16)).slice(-2);
    return '#' + r + g + b;
  }

  root.ContrastGuard = {
    luminanceFromHex: luminanceFromHex,
    contrastRatio: contrastRatio,
    textColorForBackground: textColorForBackground,
    applyContrastFg: applyContrastFg
  };
})(typeof window !== 'undefined' ? window : this);
