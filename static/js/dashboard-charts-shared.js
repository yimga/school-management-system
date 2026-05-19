/**
 * Dashboard Charts Shared - Chart.js config, colors, helpers.
 * Lazy-load Chart.js; provide consistent styling, empty-state, export.
 * On backend (body.portal-backend-dark / portal-backend-light), uses CSS vars for palette and axis/legend colors.
 */

(function () {
  'use strict';

  // Semantic colors - matches Bootstrap + school branding (fallback when not on backend)
  const CHART_COLORS = {
    primary: 'rgba(13, 110, 253, 0.8)',
    primaryLight: 'rgba(13, 110, 253, 0.15)',
    success: 'rgba(25, 135, 84, 0.8)',
    successLight: 'rgba(25, 135, 84, 0.15)',
    warning: 'rgba(255, 193, 7, 0.8)',
    warningLight: 'rgba(255, 193, 7, 0.15)',
    danger: 'rgba(220, 53, 69, 0.8)',
    dangerLight: 'rgba(220, 53, 69, 0.15)',
    secondary: 'rgba(108, 117, 125, 0.8)',
    secondaryLight: 'rgba(108, 117, 125, 0.15)',
    palette: [
      'rgba(13, 110, 253, 0.85)',
      'rgba(25, 135, 84, 0.85)',
      'rgba(255, 193, 7, 0.85)',
      'rgba(220, 53, 69, 0.85)',
      'rgba(111, 66, 193, 0.85)',
      'rgba(13, 202, 240, 0.85)',
      'rgba(253, 126, 20, 0.85)',
    ]
  };

  function isBackendPage() {
    if (typeof document === 'undefined' || !document.body) return false;
    return document.body.classList.contains('portal-backend-dark') || document.body.classList.contains('portal-backend-light');
  }

  function getBackendPreset() {
    if (!isBackendPage() || typeof document === 'undefined' || !document.body) return 'executive';
    const preset = String(document.body.dataset.backendPreset || '').toLowerCase();
    if (preset === 'operational' || preset === 'analytical' || preset === 'executive') return preset;
    if (document.body.classList.contains('backend-preset-operational')) return 'operational';
    if (document.body.classList.contains('backend-preset-analytical')) return 'analytical';
    return 'executive';
  }

  function getComputedVar(name) {
    if (typeof document === 'undefined' || !document.documentElement) return null;
    return getComputedStyle(document.body).getPropertyValue(name).trim() || null;
  }

  function clamp01(value) {
    const n = Number(value);
    if (Number.isNaN(n)) return 1;
    return Math.max(0, Math.min(1, n));
  }

  function parseColorToRgb(color) {
    if (!color) return null;
    const v = String(color).trim();
    const hex = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (hex) {
      const raw = hex[1];
      if (raw.length === 3) {
        return {
          r: parseInt(raw[0] + raw[0], 16),
          g: parseInt(raw[1] + raw[1], 16),
          b: parseInt(raw[2] + raw[2], 16),
        };
      }
      return {
        r: parseInt(raw.slice(0, 2), 16),
        g: parseInt(raw.slice(2, 4), 16),
        b: parseInt(raw.slice(4, 6), 16),
      };
    }
    const rgb = v.match(/^rgba?\(\s*([0-9.]+)\s*[, ]\s*([0-9.]+)\s*[, ]\s*([0-9.]+)/i);
    if (rgb) {
      return {
        r: Math.round(parseFloat(rgb[1])),
        g: Math.round(parseFloat(rgb[2])),
        b: Math.round(parseFloat(rgb[3])),
      };
    }
    return null;
  }

  function colorWithAlpha(color, alpha) {
    const rgb = parseColorToRgb(color);
    if (!rgb) return color;
    return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${clamp01(alpha)})`;
  }

  function createVerticalGradient(ctx, fromColor, toColor) {
    if (!ctx || !ctx.canvas) return fromColor;
    const g = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height || 220);
    g.addColorStop(0, fromColor);
    g.addColorStop(1, toColor);
    return g;
  }

  function buildThemePalette() {
    // All values flow from design-tokens.css; fallback hex literals remain only as a defensive
    // last resort if CSS tokens fail to load. Order matches --chart-color-1..6.
    const primary = getComputedVar('--dashboard-theme-primary') || getComputedVar('--brand-primary') || getComputedVar('--chart-color-1') || '#3b82f6';
    const accent = getComputedVar('--dashboard-theme-accent') || getComputedVar('--brand-accent') || getComputedVar('--chart-color-2') || '#22c55e';
    const success = getComputedVar('--brand-success') || getComputedVar('--ds-success') || '#16a34a';
    const warning = getComputedVar('--brand-warning') || getComputedVar('--ds-warning') || '#f59e0b';
    const danger = getComputedVar('--brand-danger') || getComputedVar('--ds-danger') || '#ef4444';
    const info = getComputedVar('--chart-color-6') || getComputedVar('--ds-info') || '#06b6d4';
    return [primary, accent, success, warning, danger, info];
  }

  /** When on backend, returns array of --chart-color-1..6 from CSS; otherwise null. */
  function getBackendChartPalette() {
    if (!isBackendPage()) return null;
    const out = [];
    for (let i = 1; i <= 6; i++) {
      const v = getComputedVar('--chart-color-' + i);
      if (v) out.push(v);
    }
    if (out.length >= 3) return out;
    return buildThemePalette();
  }

  /** When on backend, returns Chart.js options for scales and legend (grid/tick/legend color from theme). */
  function getBackendChartOptions() {
    if (!isBackendPage()) return {};
    const chartText = getComputedVar('--chart-text') || getComputedVar('--backend-text-muted') || getComputedVar('--color-base-400') || '#94a3b8';
    const chartGrid = getComputedVar('--chart-grid') || getComputedVar('--backend-border') || 'rgba(148, 163, 184, 0.2)';
    return {
      scales: {
        x: {
          ticks: { color: chartText },
          grid: { color: chartGrid }
        },
        y: {
          ticks: { color: chartText },
          grid: { color: chartGrid }
        }
      },
      plugins: {
        legend: {
          labels: { color: chartText }
        },
        tooltip: {
          titleColor: chartText,
          bodyColor: chartText
        }
      }
    };
  }

  function applyPaletteToDatasets(data, palette, chartType, ctx) {
    if (!data || !data.datasets || !Array.isArray(palette) || palette.length === 0) return data;
    const normalizedType = String(chartType || '').toLowerCase();
    const preset = getBackendPreset();
    const datasets = data.datasets.map(function (ds, i) {
      const c = palette[i % palette.length];
      const out = { ...ds };
      const userSet = {
        fill: ds.fill !== undefined,
        tension: ds.tension !== undefined,
        borderWidth: ds.borderWidth !== undefined,
        pointRadius: ds.pointRadius !== undefined,
        borderRadius: ds.borderRadius !== undefined,
        maxBarThickness: ds.maxBarThickness !== undefined,
        hoverOffset: ds.hoverOffset !== undefined,
      };
      if (normalizedType === 'line') {
        if (out.borderColor === undefined) out.borderColor = colorWithAlpha(c, 0.95);
        if (out.backgroundColor === undefined) {
          out.backgroundColor = createVerticalGradient(
            ctx,
            colorWithAlpha(c, 0.42),
            colorWithAlpha(c, 0.03)
          );
        }
        if (out.fill === undefined) out.fill = true;
        if (out.tension === undefined) out.tension = 0.35;
        if (out.borderWidth === undefined) out.borderWidth = 2.2;
        if (out.pointRadius === undefined) out.pointRadius = 2;
        if (out.pointBackgroundColor === undefined) out.pointBackgroundColor = colorWithAlpha(c, 0.95);
        if (out.pointBorderColor === undefined) out.pointBorderColor = colorWithAlpha(c, 1);
        if (out.pointBorderWidth === undefined) out.pointBorderWidth = 1;
        if (out.pointHoverRadius === undefined) out.pointHoverRadius = 4;
        if (out.pointHoverBorderWidth === undefined) out.pointHoverBorderWidth = 2;
        if (out.pointHoverBackgroundColor === undefined) out.pointHoverBackgroundColor = colorWithAlpha(c, 1);
        if (preset === 'executive') {
          if (!userSet.tension) out.tension = 0.4;
          if (!userSet.borderWidth) out.borderWidth = 2.4;
          if (!userSet.pointRadius) out.pointRadius = 1;
        } else if (preset === 'operational') {
          if (!userSet.fill) out.fill = false;
          if (!userSet.tension) out.tension = 0.28;
          if (!userSet.borderWidth) out.borderWidth = 2;
        } else if (preset === 'analytical') {
          if (!userSet.tension) out.tension = 0.22;
          if (!userSet.borderWidth) out.borderWidth = 2.3;
          if (!userSet.pointRadius) out.pointRadius = 3;
        }
      } else if (normalizedType === 'bar') {
        if (out.backgroundColor === undefined) out.backgroundColor = colorWithAlpha(c, 0.78);
        if (out.borderColor === undefined) out.borderColor = colorWithAlpha(c, 0.95);
        if (out.borderWidth === undefined) out.borderWidth = 1;
        if (out.borderRadius === undefined) out.borderRadius = 6;
        if (out.hoverBackgroundColor === undefined) out.hoverBackgroundColor = colorWithAlpha(c, 0.94);
        if (out.hoverBorderColor === undefined) out.hoverBorderColor = colorWithAlpha(c, 1);
        if (out.barPercentage === undefined) out.barPercentage = 0.66;
        if (out.categoryPercentage === undefined) out.categoryPercentage = 0.64;
        if (out.maxBarThickness === undefined) out.maxBarThickness = 20;
        if (preset === 'operational') {
          if (!userSet.borderRadius) out.borderRadius = 4;
          if (!userSet.maxBarThickness) out.maxBarThickness = 18;
        } else if (preset === 'analytical') {
          if (!userSet.borderRadius) out.borderRadius = 8;
          if (!userSet.maxBarThickness) out.maxBarThickness = 24;
        }
      } else if (normalizedType === 'pie' || normalizedType === 'doughnut' || normalizedType === 'polararea') {
        if (out.backgroundColor === undefined) {
          out.backgroundColor = palette.map(function (pc) { return colorWithAlpha(pc, 0.9); });
        }
        if (out.borderColor === undefined) {
          out.borderColor = palette.map(function (pc) { return colorWithAlpha(pc, 1); });
        }
        if (out.borderWidth === undefined) out.borderWidth = 1;
        if (out.hoverOffset === undefined) out.hoverOffset = 6;
        if (preset === 'operational' && !userSet.hoverOffset) out.hoverOffset = 4;
        if (preset === 'analytical' && !userSet.hoverOffset) out.hoverOffset = 8;
      } else {
        if (out.backgroundColor === undefined) out.backgroundColor = c;
        if (out.borderColor === undefined) out.borderColor = c;
      }
      return out;
    });
    return { ...data, datasets };
  }

  // Status -> color mapping for finance/requests
  const STATUS_COLORS = {
    DRAFT: CHART_COLORS.secondary,
    ISSUED: CHART_COLORS.primary,
    PARTIAL: CHART_COLORS.warning,
    PAID: CHART_COLORS.success,
    OVERDUE: CHART_COLORS.danger,
    VOID: CHART_COLORS.secondary,
    PENDING: CHART_COLORS.warning,
    APPROVED: CHART_COLORS.success,
    DENIED: CHART_COLORS.danger,
    CLARIFICATION_REQUESTED: CHART_COLORS.warning,
    PROCESSING: CHART_COLORS.primary,
    COMPLETED: CHART_COLORS.success,
  };

  const defaultOptions = {
    responsive: true,
    maintainAspectRatio: true,
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          font: { size: 11 },
          padding: 12,
          usePointStyle: true,
        }
      },
      tooltip: {
        titleFont: { size: 12 },
        bodyFont: { size: 11 },
      }
    }
  };

  function getStatusColor(status) {
    return STATUS_COLORS[String(status).toUpperCase()] || CHART_COLORS.palette[0];
  }

  /** If the chart card, wrapper, or any ancestor has data-chart-fill-container="true", use maintainAspectRatio: false so the chart fills the container. */
  function shouldFillContainer(canvas) {
    if (!canvas || !canvas.closest) return false;
    const el = canvas.closest('[data-chart-fill-container="true"]');
    return !!el;
  }

  function createChart(canvasId, config) {
    if (typeof Chart === 'undefined') {
      console.warn('Chart.js not loaded. Charts will not render.');
      return null;
    }
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    let mergedOptions = {
      ...defaultOptions,
      ...(config.options || {}),
      plugins: {
        ...defaultOptions.plugins,
        ...(config.options && config.options.plugins || {}),
      }
    };

    if (shouldFillContainer(canvas)) {
      mergedOptions.maintainAspectRatio = false;
    }

    if (isBackendPage()) {
      const backendOpts = getBackendChartOptions();
      if (backendOpts.scales) {
        mergedOptions.scales = mergedOptions.scales || {};
        if (backendOpts.scales.x) {
          mergedOptions.scales.x = { ...mergedOptions.scales.x, ...backendOpts.scales.x };
        }
        if (backendOpts.scales.y) {
          mergedOptions.scales.y = { ...mergedOptions.scales.y, ...backendOpts.scales.y };
        }
      }
      if (backendOpts.plugins) {
        mergedOptions.plugins = mergedOptions.plugins || {};
        if (backendOpts.plugins.legend) {
          mergedOptions.plugins.legend = { ...mergedOptions.plugins.legend, ...backendOpts.plugins.legend };
          if (backendOpts.plugins.legend.labels) {
            mergedOptions.plugins.legend.labels = { ...mergedOptions.plugins.legend.labels, ...backendOpts.plugins.legend.labels };
          }
        }
        if (backendOpts.plugins.tooltip) {
          mergedOptions.plugins.tooltip = { ...mergedOptions.plugins.tooltip, ...backendOpts.plugins.tooltip };
        }
      }
    }

    let chartData = config.data;
    if (isBackendPage() && chartData) {
      const palette = getBackendChartPalette();
      const preset = getBackendPreset();
      if (palette && palette.length) {
        chartData = applyPaletteToDatasets(chartData, palette, config.type, ctx);
      }
      if (preset === 'analytical') {
        mergedOptions.scales = mergedOptions.scales || {};
        mergedOptions.scales.x = { ...(mergedOptions.scales.x || {}), grid: { ...((mergedOptions.scales.x || {}).grid || {}), lineWidth: 1 } };
        mergedOptions.scales.y = { ...(mergedOptions.scales.y || {}), grid: { ...((mergedOptions.scales.y || {}).grid || {}), lineWidth: 1 } };
      } else if (preset === 'executive') {
        mergedOptions.plugins = mergedOptions.plugins || {};
        mergedOptions.plugins.legend = { ...(mergedOptions.plugins.legend || {}), position: 'bottom' };
      } else if (preset === 'operational') {
        mergedOptions.plugins = mergedOptions.plugins || {};
        mergedOptions.plugins.legend = { ...(mergedOptions.plugins.legend || {}), position: 'bottom' };
      }
      if (String(config.type || '').toLowerCase() === 'doughnut' && mergedOptions.cutout === undefined) {
        mergedOptions.cutout = preset === 'operational' ? '56%' : (preset === 'analytical' ? '66%' : '62%');
      }
    }

    return new Chart(ctx, {
      type: config.type || 'bar',
      data: chartData,
      options: mergedOptions,
    });
  }

  function exportChartToPng(chartInstance, filename) {
    if (!chartInstance || !chartInstance.canvas) return;
    const link = document.createElement('a');
    link.download = filename || 'chart.png';
    link.href = chartInstance.canvas.toDataURL('image/png');
    link.click();
  }

  function hasData(data) {
    if (!data) return false;
    if (Array.isArray(data)) return data.length > 0;
    if (data.datasets) return data.datasets.some(ds => (ds.data || []).length > 0);
    if (data.labels && data.datasets) return data.labels.length > 0;
    return false;
  }

  function fillGapsInTimeSeries(labels, values, fillWithZero) {
    fillWithZero = fillWithZero !== false;
    const result = [...values];
    for (let i = 0; i < result.length; i++) {
      if (result[i] === undefined || result[i] === null || isNaN(result[i])) {
        result[i] = fillWithZero ? 0 : (result[i - 1] || 0);
      }
    }
    return result;
  }

  /**
   * Palette aligned with unified SVG analytics (rmc-analytics-viz.css --chart-color-*).
   * Chart.js dashboards should prefer getUnifiedVizPalette() over hardcoded CHART_COLORS.
   */
  function getUnifiedVizPalette() {
    var out = [];
    for (var i = 1; i <= 6; i++) {
      var token = getComputedVar('--chart-color-' + i);
      if (token) out.push(token);
    }
    if (out.length >= 3) return out;
    return getBackendChartPalette() || buildThemePalette();
  }

  // Expose globally for templates and other scripts
  window.DashboardChartsShared = {
    CHART_COLORS,
    STATUS_COLORS,
    getStatusColor,
    createChart,
    shouldFillContainer,
    exportChartToPng,
    hasData,
    fillGapsInTimeSeries,
    defaultOptions,
    getBackendChartPalette,
    getBackendChartOptions,
    getUnifiedVizPalette,
  };
})();
