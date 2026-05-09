(function() {
  function initTeacherCharts() {
    if (typeof Chart === 'undefined' || !window.DashboardChartsShared) return;
    var shared = window.DashboardChartsShared;
    var charts = {};
    ['teacherCompletionChart', 'teacherMarksDonutChart'].forEach(function(chartId) {
      var configEl = document.querySelector('[data-chart-config="' + chartId + '"]');
      if (!configEl) return;
      try {
        var config = JSON.parse(configEl.textContent);
        if (!config.data || !config.data.labels || config.data.labels.length === 0) {
          document.querySelector('[data-chart-empty="' + chartId + '"]')?.classList.remove('d-none');
          var c = document.getElementById(chartId);
          if (c) c.style.display = 'none';
          return;
        }
        var ds = config.data.datasets && config.data.datasets[0];
        var hasValues = ds && ds.data && ds.data.some(function(v){ return (v || 0) > 0; });
        if (!hasValues && (config.type === 'doughnut' || config.type === 'pie')) {
          document.querySelector('[data-chart-empty="' + chartId + '"]')?.classList.remove('d-none');
          var c = document.getElementById(chartId);
          if (c) c.style.display = 'none';
          return;
        }
        charts[chartId] = shared.createChart(chartId, config);
      } catch (e) { console.warn('Teacher chart init:', chartId, e); }
    });
    document.querySelectorAll('[data-chart-export]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var id = this.getAttribute('data-chart-export');
        if (charts[id]) shared.exportChartToPng(charts[id], 'teacher-chart-' + id + '.png');
      });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTeacherCharts);
  } else {
    initTeacherCharts();
  }
})();
