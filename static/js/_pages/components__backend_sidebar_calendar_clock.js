(function() {
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function updateClock() {
    var now = new Date();
    var timeEl = document.getElementById('backendClockTime');
    var dateEl = document.getElementById('backendClockDate');
    if (timeEl) timeEl.textContent = pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
    if (dateEl) dateEl.textContent = now.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  }
  function renderMiniCalendar() {
    var dowEl = document.getElementById('backendCalendarDOW');
    var grid = document.getElementById('backendCalendarGrid');
    if (!dowEl || !grid) return;
    var now = new Date();
    var year = now.getFullYear();
    var month = now.getMonth();
    var first = new Date(year, month, 1);
    var last = new Date(year, month + 1, 0);
    var startPad = first.getDay();
    var days = last.getDate();
    var labels = ['S','M','T','W','T','F','S'];
    var dowHtml = '';
    labels.forEach(function(l) { dowHtml += '<span class="backend-cal-dow-cell">' + l + '</span>'; });
    dowEl.innerHTML = dowHtml;
    var gridHtml = '';
    for (var i = 0; i < startPad; i++) gridHtml += '<span class="backend-cal-cell backend-cal-empty">—</span>';
    for (var d = 1; d <= days; d++) {
      var cls = 'backend-cal-cell' + (d === now.getDate() ? ' backend-cal-today' : '');
      gridHtml += '<span class="' + cls + '">' + d + '</span>';
    }
    grid.innerHTML = gridHtml;
  }
  function init() {
    updateClock();
    renderMiniCalendar();
    setInterval(updateClock, 1000);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
