(function() {
  function initFinanceCharts() {
    if (typeof Chart === 'undefined' || !window.DashboardChartsShared) return;
    var shared = window.DashboardChartsShared;
    var charts = {};

    function initChart(chartId) {
      var configEl = document.querySelector('[data-chart-config="' + chartId + '"]');
      if (!configEl) return;
      var config;
      try {
        config = JSON.parse(configEl.textContent);
      } catch (e) {
        console.warn('Finance chart config parse error:', chartId, e);
        return;
      }
      if (!config.data || !config.data.labels || config.data.labels.length === 0) {
        document.querySelector('[data-chart-empty="' + chartId + '"]')?.classList.remove('d-none');
        document.getElementById(chartId).style.display = 'none';
        return;
      }
      var ds = config.data.datasets && config.data.datasets[0];
      var hasValues = ds && ds.data && ds.data.some(function(v){ return (v || 0) > 0; });
      if (!hasValues && (config.type === 'doughnut' || config.type === 'pie')) {
        document.querySelector('[data-chart-empty="' + chartId + '"]')?.classList.remove('d-none');
        document.getElementById(chartId).style.display = 'none';
        return;
      }
      var chart = shared.createChart(chartId, config);
      if (chart) charts[chartId] = chart;
    }

    ['financeInvoiceStatusChart', 'financeInvoiceTrendChart'].forEach(initChart);

    document.querySelectorAll('[data-chart-export]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var id = this.getAttribute('data-chart-export');
        if (charts[id]) shared.exportChartToPng(charts[id], 'finance-chart-' + id + '.png');
      });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFinanceCharts);
  } else {
    initFinanceCharts();
  }
})();
