/**
 * Dashboard Charts Shared - Chart.js config, colors, helpers.
 * Lazy-load Chart.js; provide consistent styling, empty-state, export.
 */

(function () {
  'use strict';

  // Semantic colors - matches Bootstrap + school branding
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

    const mergedOptions = {
      ...defaultOptions,
      ...(config.options || {}),
      plugins: {
        ...defaultOptions.plugins,
        ...(config.options && config.options.plugins || {}),
      }
    };

    return new Chart(ctx, {
      type: config.type || 'bar',
      data: config.data,
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
  };
})();
