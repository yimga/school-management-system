(function () {
  'use strict';

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function renderChecks(listEl, payload) {
    if (!listEl || !payload || !payload.checks) return;
    listEl.innerHTML = '';
    payload.checks.forEach(function (check) {
      var li = document.createElement('li');
      li.className =
        'list-group-item d-flex flex-wrap align-items-start justify-content-between gap-2';
      var badgeClass =
        check.status === 'pass'
          ? 'bg-success'
          : check.status === 'warn'
            ? 'bg-warning text-dark'
            : 'bg-danger';
      li.innerHTML =
        '<div><strong>' +
        check.label +
        '</strong><p class="small text-secondary mb-0">' +
        check.detail +
        '</p></div><div class="d-flex align-items-center gap-2"><span class="badge ' +
        badgeClass +
        '">' +
        check.status +
        '</span>' +
        (check.remedy_url
          ? '<a href="' +
            check.remedy_url +
            '" class="btn btn-sm btn-link">' +
            (check.remedy_label || 'Fix') +
            '</a>'
          : '') +
        '</div>';
      listEl.appendChild(li);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('rmc-diagnostics-refresh');
    if (!btn) return;
    var url = btn.getAttribute('data-api-url');
    var listEl = document.getElementById('rmc-diagnostics-list');
    btn.addEventListener('click', function () {
      btn.disabled = true;
      fetch(url, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json', 'X-CSRFToken': csrfToken() },
      })
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          renderChecks(listEl, data);
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  });
})();
