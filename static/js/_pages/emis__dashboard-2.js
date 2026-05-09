(function() {
  function initEmisChart() {
    if (typeof Chart === 'undefined' || !window.DashboardChartsShared) return;
    var configEl = document.querySelector('[data-chart-config="emisEntityChart"]');
    if (!configEl) return;
    try {
      var config = JSON.parse(configEl.textContent);
      if (config.data && config.data.labels && config.data.labels.length > 0) {
        var ch = window.DashboardChartsShared.createChart('emisEntityChart', config);
        if (ch) {
          document.querySelectorAll('[data-chart-export="emisEntityChart"]').forEach(function(btn) {
            btn.addEventListener('click', function() {
              window.DashboardChartsShared.exportChartToPng(ch, 'emis-entities.png');
            });
          });
        }
      } else {
        document.querySelector('[data-chart-empty="emisEntityChart"]')?.classList.remove('d-none');
        var c = document.getElementById('emisEntityChart');
        if (c) c.style.display = 'none';
      }
    } catch (e) { console.warn('EMIS chart init:', e); }
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', initEmisChart) : initEmisChart();
})();
