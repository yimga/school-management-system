(function () {
  function escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }
  function escAttr(s) {
    return escHtml(s).replace(/"/g, '&quot;');
  }
  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('insight-anomaly-refresh-btn');
    var root = document.getElementById('insight-anomaly-strip-root');
    if (!btn || !root) return;
    var url = btn.getAttribute('data-url');
    if (!url) return;
    var emptyMsg = btn.getAttribute('data-empty-msg') || 'No ranked anomalies right now.';
    var errMsg = btn.getAttribute('data-error-msg') || 'Could not refresh insights.';
    function render(data) {
      var list = (data && data.anomalies) || [];
      root.innerHTML = '';
      if (!list.length) {
        var empty = document.createElement('div');
        empty.className = 'col-12';
        empty.id = 'insight-anomaly-empty';
        empty.innerHTML =
          '<p class="small text-muted mb-0">' + escHtml(emptyMsg) + '</p>';
        root.appendChild(empty);
        return;
      }
      list.forEach(function (a) {
        var sev =
          a.severity === 'danger' ? 'border-danger' : 'border-warning';
        var col = document.createElement('div');
        col.className = 'col-md-6 col-xl-4 insight-anomaly-card';
        var line =
          a.insight_line
            ? '<p class="small fst-italic text-muted mb-1">' +
              escHtml(a.insight_line) +
              '</p>'
            : '';
        col.innerHTML =
          '<div class="card h-100 shadow-sm ' +
          sev +
          ' border-start border-3"><div class="card-body py-3"><h3 class="h6 mb-1">' +
          escHtml(a.title) +
          '</h3>' +
          line +
          '<p class="small text-muted mb-2">' +
          escHtml(a.detail) +
          '</p><a href="' +
          escAttr(a.action_url) +
          '" class="btn btn-sm btn-primary">' +
          escHtml(a.action_label) +
          '</a></div></div>';
        root.appendChild(col);
      });
    }
    btn.addEventListener('click', function () {
      btn.disabled = true;
      fetch(url, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then(function (r) {
          return r.json();
        })
        .then(render)
        .catch(function () {
          root.innerHTML =
            '<div class="col-12"><p class="small text-danger mb-0">' +
            escHtml(errMsg) +
            '</p></div>';
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  });
})();
