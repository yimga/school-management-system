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

  function getComputedVar(name) {
    if (typeof document === 'undefined' || !document.documentElement) return null;
    return getComputedStyle(document.body).getPropertyValue(name).trim() || null;
  }

  /** When on backend, returns array of --chart-color-1..6 from CSS; otherwise null. */
  function getBackendChartPalette() {
    if (!isBackendPage()) return null;
    const out = [];
    for (let i = 1; i <= 6; i++) {
      const v = getComputedVar('--chart-color-' + i);
      if (v) out.push(v);
    }
    return out.length >= 3 ? out : null;
  }

  /** When on backend, returns Chart.js options for scales and legend (grid/tick/legend color from theme). */
  function getBackendChartOptions() {
    if (!isBackendPage()) return {};
    const chartText = getComputedVar('--chart-text') || getComputedVar('--backend-text-muted') || '#94a3b8';
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

  function applyPaletteToDatasets(data, palette) {
    if (!data || !data.datasets || !Array.isArray(palette) || palette.length === 0) return data;
    const datasets = data.datasets.map(function (ds, i) {
      const c = palette[i % palette.length];
      const out = { ...ds };
      if (out.backgroundColor === undefined) out.backgroundColor = c;
      if (out.borderColor === undefined) out.borderColor = c;
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
      if (palette && palette.length) {
        chartData = applyPaletteToDatasets(chartData, palette);
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

  // Expose globally for templates and other scripts
  window.DashboardChartsShared = {
    CHART_COLORS,
    STATUS_COLORS,
    getStatusColor,
    createChart,
    exportChartToPng,
    hasData,
    fillGapsInTimeSeries,
    defaultOptions,
    getBackendChartPalette,
    getBackendChartOptions,
  };
})();
