(function() {
  function initAnalyticsCharts() {
    if (typeof Chart === 'undefined' || !window.DashboardChartsShared) return;
    var shared = window.DashboardChartsShared;
    var charts = {};
    ['analyticsWeakSubjectsChart', 'analyticsSpecialtyChart'].forEach(function(chartId) {
      var configEl = document.querySelector('[data-chart-config="' + chartId + '"]');
      if (!configEl) return;
      try {
        var config = JSON.parse(configEl.textContent);
        if (!config.data || !config.data.labels) {
          document.querySelector('[data-chart-empty="' + chartId + '"]')?.classList.remove('d-none');
          var c = document.getElementById(chartId);
          if (c) c.style.display = 'none';
          return;
        }
        var ds = config.data.datasets && config.data.datasets[0];
        var hasValues = !ds || !ds.data || ds.data.some(function(v){ return (v || 0) > 0; });
        if (!hasValues && (config.type === 'doughnut' || config.type === 'pie')) {
          document.querySelector('[data-chart-empty="' + chartId + '"]')?.classList.remove('d-none');
          var c = document.getElementById(chartId);
          if (c) c.style.display = 'none';
          return;
        }
        var ch = shared.createChart(chartId, config);
        if (ch) charts[chartId] = ch;
      } catch (e) { console.warn('Analytics chart init:', chartId, e); }
    });
    document.querySelectorAll('[data-chart-export]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var id = this.getAttribute('data-chart-export');
        if (charts[id]) shared.exportChartToPng(charts[id], 'analytics-' + id + '.png');
      });
    });
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', initAnalyticsCharts) : initAnalyticsCharts();
})();
