(function () {
  'use strict';

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function showDenied(message) {
    if (window.RMCInteractionGuard && window.RMCInteractionGuard.permissionBanner) {
      window.RMCInteractionGuard.permissionBanner(message);
      return;
    }
    var host = document.getElementById('rmc-perm-sim-denied');
    if (!host) return;
    host.textContent = message;
    host.classList.remove('d-none');
  }

  function notifyError(message) {
    if (window.RMCInteractionGuard && window.RMCInteractionGuard.notify) {
      window.RMCInteractionGuard.notify(message, 'error');
    } else if (typeof window.showToast === 'function') {
      window.showToast(message, 'error', 5000);
    }
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var liveBtn = document.getElementById('rmc-perm-sim-live');
    var roleSelect = document.getElementById('role-select');
    var tbody = document.querySelector('#rmc-perm-matrix-table tbody');
    if (!liveBtn || !roleSelect || !tbody) return;

    liveBtn.addEventListener('click', function () {
      var url = liveBtn.getAttribute('data-api-url');
      liveBtn.disabled = true;
      var denied = document.getElementById('rmc-perm-sim-denied');
      if (denied) denied.classList.add('d-none');

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
          if (res.status === 403 || res.status === 401) {
            showDenied(
              'You do not have permission to run live simulations. Contact a settings administrator.'
            );
            return null;
          }
          if (!res.ok) {
            throw new Error('simulate_failed_' + res.status);
          }
          return res.json();
        })
        .then(function (data) {
          if (!data || !data.capabilities) return;
          tbody.innerHTML = '';
          data.capabilities.forEach(function (cap) {
            var tr = document.createElement('tr');
            var reasons = (cap.reasons || [])
              .map(function (r) {
                return '<li>' + escapeHtml(r) + '</li>';
              })
              .join('');
            tr.innerHTML =
              '<td>' +
              escapeHtml(cap.label) +
              '</td><td><span class="badge ' +
              (cap.visible ? 'bg-success' : 'bg-secondary') +
              '">' +
              (cap.visible ? 'Yes' : 'No') +
              '</span></td><td>' +
              (cap.school_action_ok ? 'OK' : 'Denied') +
              '</td><td>' +
              (cap.feature_ok ? 'OK' : 'Denied') +
              '</td><td><code class="small">' +
              escapeHtml(cap.pdp_effect) +
              '</code></td><td class="small text-secondary"><ul class="mb-0 ps-3">' +
              reasons +
              '</ul></td>';
            tbody.appendChild(tr);
          });
        })
        .catch(function () {
          notifyError(
            'Action currently unavailable — please contact your administrator.'
          );
        })
        .finally(function () {
          liveBtn.disabled = false;
        });
    });
  });
})();
