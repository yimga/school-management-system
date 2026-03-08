/**
 * Color Harmony Engine
 * Pure JS for HEX <-> HSL conversions and color harmony generation.
 * No external dependencies.
 */
(function (global) {
  'use strict';

  var colorHarmony = {};

  // ============================================================
  // HEX <-> RGB <-> HSL Conversions
  // ============================================================

  /**
   * Normalize a hex string to 6-digit lowercase with #
   * @param {string} hex
   * @returns {string}
   */
  function normalizeHex(hex) {
    if (!hex || typeof hex !== 'string') return '#ffffff';
    hex = hex.trim().toLowerCase();
    if (!hex.startsWith('#')) hex = '#' + hex;
    if (hex.length === 4) {
      hex = '#' + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3];
    }
    if (!/^#[0-9a-f]{6}$/.test(hex)) return '#ffffff';
    return hex;
  }

  /**
   * HEX to RGB
   * @param {string} hex
   * @returns {{r: number, g: number, b: number}}
   */
  function hexToRgb(hex) {
    hex = normalizeHex(hex);
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return { r: r, g: g, b: b };
  }

  /**
   * RGB to HEX
   * @param {number} r
   * @param {number} g
   * @param {number} b
   * @returns {string}
   */
  function rgbToHex(r, g, b) {
    r = Math.round(Math.max(0, Math.min(255, r)));
    g = Math.round(Math.max(0, Math.min(255, g)));
    b = Math.round(Math.max(0, Math.min(255, b)));
    return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
  }

  /**
   * RGB to HSL
   * @param {number} r (0-255)
   * @param {number} g (0-255)
   * @param {number} b (0-255)
   * @returns {{h: number, s: number, l: number}} h (0-360), s (0-100), l (0-100)
   */
  function rgbToHsl(r, g, b) {
    r /= 255;
    g /= 255;
    b /= 255;
    var max = Math.max(r, g, b);
    var min = Math.min(r, g, b);
    var h, s, l = (max + min) / 2;

    if (max === min) {
      h = s = 0;
    } else {
      var d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case r:
          h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
          break;
        case g:
          h = ((b - r) / d + 2) / 6;
          break;
        case b:
          h = ((r - g) / d + 4) / 6;
          break;
      }
    }
    return { h: h * 360, s: s * 100, l: l * 100 };
  }

  /**
   * HSL to RGB
   * @param {number} h (0-360)
   * @param {number} s (0-100)
   * @param {number} l (0-100)
   * @returns {{r: number, g: number, b: number}}
   */
  function hslToRgb(h, s, l) {
    h = ((h % 360) + 360) % 360;
    s = Math.max(0, Math.min(100, s)) / 100;
    l = Math.max(0, Math.min(100, l)) / 100;

    var c = (1 - Math.abs(2 * l - 1)) * s;
    var x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    var m = l - c / 2;
    var r, g, b;

    if (h < 60) {
      r = c; g = x; b = 0;
    } else if (h < 120) {
      r = x; g = c; b = 0;
    } else if (h < 180) {
      r = 0; g = c; b = x;
    } else if (h < 240) {
      r = 0; g = x; b = c;
    } else if (h < 300) {
      r = x; g = 0; b = c;
    } else {
      r = c; g = 0; b = x;
    }

    return {
      r: Math.round((r + m) * 255),
      g: Math.round((g + m) * 255),
      b: Math.round((b + m) * 255)
    };
  }

  /**
   * HEX to HSL
   * @param {string} hex
   * @returns {{h: number, s: number, l: number}}
   */
  function hexToHsl(hex) {
    var rgb = hexToRgb(hex);
    return rgbToHsl(rgb.r, rgb.g, rgb.b);
  }

  /**
   * HSL to HEX
   * @param {number} h
   * @param {number} s
   * @param {number} l
   * @returns {string}
   */
  function hslToHex(h, s, l) {
    var rgb = hslToRgb(h, s, l);
    return rgbToHex(rgb.r, rgb.g, rgb.b);
  }

  // ============================================================
  // Color Harmony Algorithms
  // ============================================================

  /**
   * Complement: Base + opposite (H + 180)
   * @param {string} hex
   * @returns {string[]} 2 colors
   */
  function complement(hex) {
    var hsl = hexToHsl(hex);
    return [
      normalizeHex(hex),
      hslToHex((hsl.h + 180) % 360, hsl.s, hsl.l)
    ];
  }

  /**
   * Split-complementary: Base + two adjacent to complement (H + 150, H + 210)
   * @param {string} hex
   * @returns {string[]} 3 colors
   */
  function splitComplementary(hex) {
    var hsl = hexToHsl(hex);
    return [
      normalizeHex(hex),
      hslToHex((hsl.h + 150) % 360, hsl.s, hsl.l),
      hslToHex((hsl.h + 210) % 360, hsl.s, hsl.l)
    ];
  }

  /**
   * Triadic: Three colors spaced 120 degrees apart
   * @param {string} hex
   * @returns {string[]} 3 colors
   */
  function triadic(hex) {
    var hsl = hexToHsl(hex);
    return [
      normalizeHex(hex),
      hslToHex((hsl.h + 120) % 360, hsl.s, hsl.l),
      hslToHex((hsl.h + 240) % 360, hsl.s, hsl.l)
    ];
  }

  /**
   * Analogous: Three adjacent colors (H - 30, H, H + 30)
   * @param {string} hex
   * @returns {string[]} 3 colors
   */
  function analogous(hex) {
    var hsl = hexToHsl(hex);
    return [
      hslToHex((hsl.h - 30 + 360) % 360, hsl.s, hsl.l),
      normalizeHex(hex),
      hslToHex((hsl.h + 30) % 360, hsl.s, hsl.l)
    ];
  }

  /**
   * Monochromatic: Same hue, different lightness (L - 25%, L, L + 25%)
   * @param {string} hex
   * @returns {string[]} 3 colors
   */
  function monochromatic(hex) {
    var hsl = hexToHsl(hex);
    var darkL = Math.max(10, hsl.l - 25);
    var lightL = Math.min(90, hsl.l + 25);
    return [
      hslToHex(hsl.h, hsl.s, darkL),
      normalizeHex(hex),
      hslToHex(hsl.h, hsl.s, lightL)
    ];
  }

  /**
   * Tetradic (rectangle): Four colors - base + 90 + 180 + 270 degrees
   * @param {string} hex
   * @returns {string[]} 4 colors
   */
  function tetradic(hex) {
    var hsl = hexToHsl(hex);
    return [
      normalizeHex(hex),
      hslToHex((hsl.h + 90) % 360, hsl.s, hsl.l),
      hslToHex((hsl.h + 180) % 360, hsl.s, hsl.l),
      hslToHex((hsl.h + 270) % 360, hsl.s, hsl.l)
    ];
  }

  /**
   * Square: Four colors equidistant (90 degrees apart). Same as tetradic geometry.
   * @param {string} hex
   * @returns {string[]} 4 colors
   */
  function square(hex) {
    return tetradic(hex);
  }

  /**
   * Achromatic: No hue — black, white, and grays. Uses input lightness to anchor scale.
   * @param {string} hex
   * @returns {string[]} 5 grays
   */
  function achromatic(hex) {
    var hsl = hexToHsl(hex);
    var L = hsl.l;
    var steps = [Math.max(8, L - 40), L - 20, L, L + 20, Math.min(95, L + 40)];
    return steps.map(function (l) {
      return hslToHex(0, 0, Math.max(5, Math.min(98, l)));
    });
  }

  /**
   * Polychromatic: Five colors evenly spaced (72 degrees). Same saturation and lightness.
   * @param {string} hex
   * @returns {string[]} 5 colors
   */
  function polychromatic(hex) {
    var hsl = hexToHsl(hex);
    var out = [normalizeHex(hex)];
    for (var i = 1; i < 5; i++) {
      out.push(hslToHex((hsl.h + 72 * i) % 360, hsl.s, hsl.l));
    }
    return out;
  }

  /**
   * Diad: Two colors separated by 60 degrees on the wheel.
   * @param {string} hex
   * @returns {string[]} 2 colors
   */
  function diad(hex) {
    var hsl = hexToHsl(hex);
    return [
      normalizeHex(hex),
      hslToHex((hsl.h + 60) % 360, hsl.s, hsl.l)
    ];
  }

  /**
   * Near-complementary: Base + color one step (30°) from true complement.
   * @param {string} hex
   * @returns {string[]} 2 colors (base + 150°)
   */
  function nearComplementary(hex) {
    var hsl = hexToHsl(hex);
    return [
      normalizeHex(hex),
      hslToHex((hsl.h + 150) % 360, hsl.s, hsl.l)
    ];
  }

  /**
   * Neutral with accent: Grays plus one bold accent (input hue at full saturation).
   * @param {string} hex
   * @returns {string[]} 4 grays + 1 accent
   */
  function neutralWithAccent(hex) {
    var hsl = hexToHsl(hex);
    var grays = ['#111111', '#555555', '#999999', '#cccccc'];
    var accent = hslToHex(hsl.h, 80, Math.max(40, Math.min(60, hsl.l)));
    return grays.concat([accent]);
  }

  /**
   * Common component: Same saturation, varying hue and lightness (shared “lens”).
   * @param {string} hex
   * @returns {string[]} 4 colors
   */
  function commonComponent(hex) {
    var hsl = hexToHsl(hex);
    var s = Math.max(40, hsl.s);
    return [
      normalizeHex(hex),
      hslToHex((hsl.h + 90) % 360, s, Math.max(20, hsl.l - 15)),
      hslToHex((hsl.h + 180) % 360, s, hsl.l),
      hslToHex((hsl.h + 270) % 360, s, Math.min(90, hsl.l + 15))
    ];
  }

  /**
   * Contrast of light/dark: Same hue, opposite ends of lightness scale.
   * @param {string} hex
   * @returns {string[]} 2 colors
   */
  function contrastLightDark(hex) {
    var hsl = hexToHsl(hex);
    return [
      hslToHex(hsl.h, hsl.s, 20),
      hslToHex(hsl.h, hsl.s, 88)
    ];
  }

  /**
   * Hue contrast: Distant hues for liveliness (base + 150°, + 210°).
   * @param {string} hex
   * @returns {string[]} 3 colors
   */
  function hueContrast(hex) {
    var hsl = hexToHsl(hex);
    return [
      normalizeHex(hex),
      hslToHex((hsl.h + 150) % 360, hsl.s, hsl.l),
      hslToHex((hsl.h + 210) % 360, hsl.s, hsl.l)
    ];
  }

  /**
   * Ostwald grey harmony: Three neutrals equally spaced in value.
   * @param {string} hex
   * @returns {string[]} 3 grays
   */
  function ostwaldGrey(hex) {
    return [
      hslToHex(0, 0, 25),
      hslToHex(0, 0, 50),
      hslToHex(0, 0, 75)
    ];
  }

  /**
   * Warm palette: Reds, oranges, yellows (hues 0–60°).
   * @param {string} hex
   * @returns {string[]} 4 colors
   */
  function warmPalette(hex) {
    var hsl = hexToHsl(hex);
    var s = Math.max(50, hsl.s);
    var l = hsl.l;
    return [
      hslToHex(0, s, l),
      hslToHex(20, s, l),
      hslToHex(40, s, l),
      hslToHex(60, s, l)
    ];
  }

  /**
   * Cool palette: Blues, greens, violets (hues 180–300°).
   * @param {string} hex
   * @returns {string[]} 4 colors
   */
  function coolPalette(hex) {
    var hsl = hexToHsl(hex);
    var s = Math.max(50, hsl.s);
    var l = hsl.l;
    return [
      hslToHex(180, s, l),
      hslToHex(220, s, l),
      hslToHex(260, s, l),
      hslToHex(300, s, l)
    ];
  }

  /**
   * Earth tones: Desaturated warm (terracotta, olive, beige).
   * @param {string} hex
   * @returns {string[]} 4 colors
   */
  function earthTones(hex) {
    var hsl = hexToHsl(hex);
    var lowS = 35;
    var l = Math.max(35, Math.min(70, hsl.l));
    return [
      hslToHex(20, lowS, l - 15),
      hslToHex(80, lowS + 10, l),
      hslToHex(45, lowS, l + 10),
      hslToHex(60, lowS - 5, l + 15)
    ];
  }

  // ============================================================
  // Preset Palettes
  // ============================================================

  var PRESETS = {
    'lively-slate': {
      name: 'Lively Slate',
      type: 'Balanced',
      colors: ['#1e293b', '#0ea5e9', '#f8fafc', '#22c55e', '#f59e0b'],
      bestFor: 'Professional admin dashboards with crisp accents'
    },
    'refined-beautified': {
      name: 'Refined (beautified)',
      type: 'Elegant',
      colors: ['#0f172a', '#7c3aed', '#e2e8f0', '#334155', '#c084fc'],
      bestFor: 'Premium school branding and executive pages'
    },
    'dark-minimal': {
      name: 'Dark minimal',
      type: 'Minimal',
      colors: ['#0b1120', '#1f2937', '#3b82f6', '#94a3b8', '#f8fafc'],
      bestFor: 'Low-glare staff interfaces and night operation'
    },
    'light-card': {
      name: 'Light card',
      type: 'Soft',
      colors: ['#0d6efd', '#14b8a6', '#f8fafc', '#ffffff', '#64748b'],
      bestFor: 'Clean parent portal and document-heavy screens'
    },
    'ink-and-onyx': {
      name: 'Ink & Onyx',
      type: 'Monochrome',
      colors: ['#020617', '#111827', '#334155', '#cbd5e1', '#f8fafc'],
      bestFor: 'Contrast-safe analytics and compliance views'
    },
    'sunrise-warm': {
      name: 'Sunrise Warm',
      type: 'Warm',
      colors: ['#dc2626', '#f59e0b', '#fde68a', '#7c2d12', '#fff7ed'],
      bestFor: 'Admissions and action-focused workflows'
    },
    'emerald-focus': {
      name: 'Emerald Focus',
      type: 'Growth',
      colors: ['#14532d', '#22c55e', '#86efac', '#0f172a', '#f0fdf4'],
      bestFor: 'Progress tracking and teacher productivity pages'
    },
    'blue-orange': {
      name: 'Blue & Orange',
      type: 'Complementary',
      colors: ['#2563eb', '#f97316'],
      bestFor: 'High-impact designs, CTAs, dashboards'
    },
    'red-green': {
      name: 'Red & Green',
      type: 'Complementary',
      colors: ['#dc2626', '#16a34a'],
      bestFor: 'Alerts, success/error states'
    },
    'purple-yellow': {
      name: 'Purple & Yellow',
      type: 'Complementary',
      colors: ['#7c3aed', '#eab308'],
      bestFor: 'Premium, academic branding'
    },
    'blue-green-purple': {
      name: 'Blue-Green & Purple',
      type: 'Analogous',
      colors: ['#0d9488', '#a855f7', '#ec4899'],
      bestFor: 'Calm, modern interfaces'
    },
    'yellow-amber-red': {
      name: 'Yellow, Amber & Red',
      type: 'Analogous',
      colors: ['#eab308', '#f59e0b', '#ef4444'],
      bestFor: 'Warm, welcoming designs'
    },
    'coral-sky-spring': {
      name: 'Coral, Sky Blue, Spring Green',
      type: 'Triadic',
      colors: ['#f97316', '#0ea5e9', '#22c55e'],
      bestFor: 'Energetic, playful designs'
    },
    'shades-blue': {
      name: 'Shades of Blue',
      type: 'Monochromatic',
      colors: ['#1e3a5f', '#0ea5e9', '#7dd3fc'],
      bestFor: 'Minimalist, professional'
    },
    'shades-green': {
      name: 'Shades of Green',
      type: 'Monochromatic',
      colors: ['#14532d', '#22c55e', '#86efac'],
      bestFor: 'Nature, growth themes'
    },
    'black-white-red': {
      name: 'Black, White & Red',
      type: 'Classic',
      colors: ['#000000', '#ffffff', '#dc2626'],
      bestFor: 'Corporate, high contrast'
    },
    'brown-blue': {
      name: 'Brown & Blue',
      type: 'Classic',
      colors: ['#a16207', '#2563eb', '#fef3c7'],
      bestFor: 'Trust, warmth'
    },
    'teal-coral': {
      name: 'Teal & Coral',
      type: 'Complementary',
      colors: ['#0d9488', '#f97316', '#fef3c7'],
      bestFor: 'Fresh, approachable dashboards'
    },
    'indigo-amber': {
      name: 'Indigo & Amber',
      type: 'Complementary',
      colors: ['#4f46e5', '#f59e0b', '#eef2ff'],
      bestFor: 'Academic, scholarly feel'
    },
    'emerald-rose': {
      name: 'Emerald & Rose',
      type: 'Complementary',
      colors: ['#059669', '#e11d48', '#ecfdf5'],
      bestFor: 'Growth, success, gentle alerts'
    },
    'slate-gold': {
      name: 'Slate & Gold',
      type: 'Complementary',
      colors: ['#475569', '#ca8a04', '#f8fafc'],
      bestFor: 'Professional, premium school branding'
    },
    'navy-mint': {
      name: 'Navy & Mint',
      type: 'Complementary',
      colors: ['#1e3a8a', '#34d399', '#f0fdf4'],
      bestFor: 'Calm, trustworthy interfaces'
    },
    'burgundy-sage': {
      name: 'Burgundy & Sage',
      type: 'Complementary',
      colors: ['#881337', '#84cc16', '#fef2f2'],
      bestFor: 'Traditional, institutional'
    },
    'violet-lime': {
      name: 'Violet & Lime',
      type: 'Complementary',
      colors: ['#6d28d9', '#84cc16', '#f5f3ff'],
      bestFor: 'Creative, modern education'
    },
    'deep-navy-gold': {
      name: 'Deep Navy & Gold',
      type: 'Complementary',
      colors: ['#0c1929', '#f59e0b', '#fef3c7'],
      bestFor: 'Executive, premium dashboards'
    },
    'sage-mauve': {
      name: 'Sage & Mauve',
      type: 'Analogous',
      colors: ['#64748b', '#a78bfa', '#c4b5fd'],
      bestFor: 'Calm, sophisticated interfaces'
    },
    'crimson-gold': {
      name: 'Crimson & Gold',
      type: 'Complementary',
      colors: ['#b91c1c', '#ca8a04', '#fef2f2'],
      bestFor: 'Academic excellence branding'
    },
    'ocean-sand': {
      name: 'Ocean & Sand',
      type: 'Analogous',
      colors: ['#0284c7', '#0ea5e9', '#fcd34d'],
      bestFor: 'Beach, summer, relaxed'
    },
    'forest-moss': {
      name: 'Forest & Moss',
      type: 'Analogous',
      colors: ['#166534', '#22c55e', '#65a30d'],
      bestFor: 'Nature, sustainability, growth'
    },
    'sunset-blush': {
      name: 'Sunset Blush',
      type: 'Analogous',
      colors: ['#ea580c', '#f97316', '#fb923c'],
      bestFor: 'Warm, inviting dashboards'
    },
    'twilight': {
      name: 'Twilight',
      type: 'Triadic',
      colors: ['#6366f1', '#22c55e', '#f59e0b'],
      bestFor: 'Vibrant, balanced school UI'
    },
    'aurora': {
      name: 'Aurora',
      type: 'Triadic',
      colors: ['#8b5cf6', '#06b6d4', '#fbbf24'],
      bestFor: 'Dynamic, memorable branding'
    },
    'shades-purple': {
      name: 'Shades of Purple',
      type: 'Monochromatic',
      colors: ['#4c1d95', '#7c3aed', '#c4b5fd'],
      bestFor: 'Creative, premium feel'
    },
    'shades-slate': {
      name: 'Shades of Slate',
      type: 'Monochromatic',
      colors: ['#0f172a', '#475569', '#94a3b8'],
      bestFor: 'Minimal, accessible dark mode'
    },
    'shades-amber': {
      name: 'Shades of Amber',
      type: 'Monochromatic',
      colors: ['#78350f', '#d97706', '#fde68a'],
      bestFor: 'Warm, readable interfaces'
    },
    'ivory-navy': {
      name: 'Ivory & Navy',
      type: 'Classic',
      colors: ['#fafaf9', '#1e3a8a', '#3b82f6'],
      bestFor: 'Clean, formal school sites'
    },
    'charcoal-accent': {
      name: 'Charcoal & Accent',
      type: 'Classic',
      colors: ['#1c1917', '#64748b', '#38bdf8'],
      bestFor: 'High-contrast, accessible'
    },
    'cream-olive': {
      name: 'Cream & Olive',
      type: 'Classic',
      colors: ['#fefce8', '#422006', '#65a30d'],
      bestFor: 'Soft, nature-inspired'
    },
    'high-contrast': {
      name: 'High Contrast',
      type: 'Classic',
      colors: ['#000000', '#ffffff', '#2563eb'],
      bestFor: 'Accessibility, readability'
    },
    'platform-blue': {
      name: 'Platform Blue',
      type: 'Classic',
      colors: ['#1e3a8a', '#3b82f6', '#93c5fd'],
      bestFor: 'Platform identity, trust'
    },
    'primary-school': {
      name: 'Primary School',
      type: 'Analogous',
      colors: ['#0d9488', '#22c55e', '#fbbf24'],
      bestFor: 'Friendly, educational'
    },
    'university-navy': {
      name: 'University Navy',
      type: 'Monochromatic',
      colors: ['#0f172a', '#1e40af', '#60a5fa'],
      bestFor: 'Academic, formal'
    },
    'campus-green': {
      name: 'Campus Green',
      type: 'Analogous',
      colors: ['#15803d', '#22c55e', '#4ade80'],
      bestFor: 'Growth, campus life'
    },
    'sunrise-accent': {
      name: 'Sunrise Accent',
      type: 'Complementary',
      colors: ['#ea580c', '#0ea5e9', '#fef3c7'],
      bestFor: 'Energetic, modern school'
    }
  };

  var CURATED_PRESET_KEYS = [
    'lively-slate',
    'refined-beautified',
    'dark-minimal',
    'light-card',
    'ink-and-onyx',
    'sunrise-warm',
    'emerald-focus',
    'high-contrast',
    'platform-blue',
    'indigo-amber',
    'twilight',
    'deep-navy-gold'
  ];

  // ============================================================
  // Harmony metadata
  // ============================================================

  var HARMONIES = {
    complement: {
      name: 'Complement',
      description: 'A color and its opposite on the color wheel (+180 degrees). High contrast.',
      bestFor: 'High-impact designs, CTAs, logos',
      fn: complement
    },
    splitComplementary: {
      name: 'Split-complementary',
      description: 'A color and two adjacent to its complement. Bold but versatile.',
      bestFor: 'Vibrant yet balanced layouts',
      fn: splitComplementary
    },
    triadic: {
      name: 'Triadic',
      description: 'Three colors spaced evenly (120 degrees apart). Best with one dominant.',
      bestFor: 'Playful, energetic designs',
      fn: triadic
    },
    analogous: {
      name: 'Analogous',
      description: 'Three adjacent colors (30 degrees apart). Smooth transitions.',
      bestFor: 'Nature-inspired, calming interfaces',
      fn: analogous
    },
    monochromatic: {
      name: 'Monochromatic',
      description: 'Same hue with different lightness values. Subtle and refined.',
      bestFor: 'Minimalist, sophisticated designs',
      fn: monochromatic
    },
    tetradic: {
      name: 'Tetradic',
      description: 'Four colors forming a rectangle on the wheel (90 degrees apart).',
      bestFor: 'Rich, diverse color schemes',
      fn: tetradic
    },
    square: {
      name: 'Square',
      description: 'Four colors at 90-degree spacing on the wheel. Balanced and bold.',
      bestFor: 'Vibrant, balanced palettes',
      fn: square
    },
    achromatic: {
      name: 'Achromatic',
      description: 'Neutrals only: black, white, and grays. No hue.',
      bestFor: 'Minimal, high-contrast, or typography-focused designs',
      fn: achromatic
    },
    polychromatic: {
      name: 'Polychromatic',
      description: 'Five colors evenly spaced (72 degrees apart). Same saturation and lightness.',
      bestFor: 'Diverse, energetic palettes',
      fn: polychromatic
    },
    diad: {
      name: 'Diad',
      description: 'Two colors separated by 60 degrees on the wheel.',
      bestFor: 'Simple two-color schemes with harmony',
      fn: diad
    }
  };

  // ============================================================
  // Utility: format as RGB string
  // ============================================================

  function hexToRgbString(hex) {
    var rgb = hexToRgb(hex);
    return 'rgb(' + rgb.r + ', ' + rgb.g + ', ' + rgb.b + ')';
  }

  function hexToHslString(hex) {
    var hsl = hexToHsl(hex);
    return 'hsl(' + Math.round(hsl.h) + ', ' + Math.round(hsl.s) + '%, ' + Math.round(hsl.l) + '%)';
  }

  // ============================================================
  // Public API
  // ============================================================

  colorHarmony.normalizeHex = normalizeHex;
  colorHarmony.hexToRgb = hexToRgb;
  colorHarmony.rgbToHex = rgbToHex;
  colorHarmony.hexToHsl = hexToHsl;
  colorHarmony.hslToHex = hslToHex;
  colorHarmony.hexToRgbString = hexToRgbString;
  colorHarmony.hexToHslString = hexToHslString;

  // Harmony functions
  colorHarmony.complement = complement;
  colorHarmony.splitComplementary = splitComplementary;
  colorHarmony.triadic = triadic;
  colorHarmony.analogous = analogous;
  colorHarmony.monochromatic = monochromatic;
  colorHarmony.tetradic = tetradic;
  colorHarmony.square = square;
  colorHarmony.achromatic = achromatic;
  colorHarmony.polychromatic = polychromatic;
  colorHarmony.diad = diad;
  colorHarmony.nearComplementary = nearComplementary;
  colorHarmony.neutralWithAccent = neutralWithAccent;
  colorHarmony.commonComponent = commonComponent;
  colorHarmony.contrastLightDark = contrastLightDark;
  colorHarmony.hueContrast = hueContrast;
  colorHarmony.ostwaldGrey = ostwaldGrey;
  colorHarmony.warmPalette = warmPalette;
  colorHarmony.coolPalette = coolPalette;
  colorHarmony.earthTones = earthTones;

  // Metadata
  colorHarmony.HARMONIES = HARMONIES;
  colorHarmony.PRESETS = PRESETS;
  colorHarmony.CURATED_PRESET_KEYS = CURATED_PRESET_KEYS.slice();

  /**
   * Generate harmony by name
   * @param {string} harmonyType - One of: complement, splitComplementary, triadic, analogous, monochromatic, tetradic, square, achromatic, polychromatic, diad, nearComplementary, neutralWithAccent, commonComponent, contrastLightDark, hueContrast, ostwaldGrey, warmPalette, coolPalette, earthTones
   * @param {string} baseHex
   * @returns {string[]}
   */
  colorHarmony.generate = function (harmonyType, baseHex) {
    var h = HARMONIES[harmonyType];
    if (h && typeof h.fn === 'function') {
      return h.fn(baseHex);
    }
    return [normalizeHex(baseHex)];
  };

  /**
   * Get preset by key
   * @param {string} key
   * @returns {object|null}
   */
  colorHarmony.getPreset = function (key) {
    return PRESETS[key] || null;
  };

  /**
   * List all preset keys
   * @returns {string[]}
   */
  colorHarmony.listPresets = function () {
    return CURATED_PRESET_KEYS.filter(function (key) {
      return !!PRESETS[key];
    });
  };

  /**
   * List all harmony types
   * @returns {string[]}
   */
  colorHarmony.listHarmonies = function () {
    return Object.keys(HARMONIES);
  };

  function buildFieldMapFromColors(colors) {
    var safe = Array.isArray(colors) ? colors : [];
    function pick(index, fallback) {
      if (!safe.length) return fallback || '';
      if (safe[index]) return safe[index];
      return safe[safe.length - 1] || fallback || '';
    }
    return {
      primary_color: pick(0, ''),
      accent_color: pick(1, pick(0, '')),
      header_bg_color: pick(0, ''),
      footer_bg_color: pick(2, pick(0, '')),
      success_color: pick(3, ''),
      warning_color: pick(4, ''),
      danger_color: pick(5, '')
    };
  }

  colorHarmony.buildFieldMapFromColors = buildFieldMapFromColors;

  colorHarmony.getPresetFieldMap = function (key) {
    var preset = PRESETS[key];
    if (!preset) return null;
    if (preset.fields && typeof preset.fields === 'object') {
      return Object.assign({}, preset.fields);
    }
    return buildFieldMapFromColors(preset.colors || []);
  };

  // Export
  global.colorHarmony = colorHarmony;

})(typeof window !== 'undefined' ? window : this);
