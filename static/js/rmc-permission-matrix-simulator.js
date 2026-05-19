(function () {
  'use strict';

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  document.addEventListener('DOMContentLoaded', function () {
    var liveBtn = document.getElementById('rmc-perm-sim-live');
    var roleSelect = document.getElementById('role-select');
    var tbody = document.querySelector('#rmc-perm-matrix-table tbody');
    if (!liveBtn || !roleSelect || !tbody) return;

    liveBtn.addEventListener('click', function () {
      var url = liveBtn.getAttribute('data-api-url');
      liveBtn.disabled = true;
      fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify({ role: roleSelect.value }),
      })
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          if (!data.capabilities) return;
          tbody.innerHTML = '';
          data.capabilities.forEach(function (cap) {
            var tr = document.createElement('tr');
            var reasons = (cap.reasons || [])
              .map(function (r) {
                return '<li>' + r + '</li>';
              })
              .join('');
            tr.innerHTML =
              '<td>' +
              cap.label +
              '</td><td><span class="badge ' +
              (cap.visible ? 'bg-success' : 'bg-secondary') +
              '">' +
              (cap.visible ? 'Yes' : 'No') +
              '</span></td><td>' +
              (cap.school_action_ok ? 'OK' : 'Denied') +
              '</td><td>' +
              (cap.feature_ok ? 'OK' : 'Denied') +
              '</td><td><code class="small">' +
              cap.pdp_effect +
              '</code></td><td class="small text-secondary"><ul class="mb-0 ps-3">' +
              reasons +
              '</ul></td>';
            tbody.appendChild(tr);
          });
        })
        .finally(function () {
          liveBtn.disabled = false;
        });
    });
  });
})();
