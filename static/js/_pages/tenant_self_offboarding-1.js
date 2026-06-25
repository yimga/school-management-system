(function () {
  'use strict';
  var root = document.querySelector('[data-rmc-tenant-offboarding]');
  if (!root) return;
  var dataEl = document.getElementById('page-data-tenant_self_offboarding-1');
  var cfg = {};
  if (dataEl && dataEl.textContent) {
    try { cfg = JSON.parse(dataEl.textContent); } catch (_e) { cfg = {}; }
  }
  var operatorOnly = !!cfg.operator_only;
  function csrf() {
    var i = document.querySelector('[name=csrfmiddlewaretoken]');
    if (i && i.value) return i.value;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }
  function status(msg, tone) {
    var el = root.querySelector('[data-rmc-tenant-offboard-status]');
    if (!el) return;
    el.textContent = msg;
    el.className = 'alert alert-' + (tone || 'secondary');
    el.classList.remove('d-none');
  }
  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), Accept: 'application/json' },
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      return r.text().then(function (t) {
        var p = null;
        try { p = t ? JSON.parse(t) : {}; } catch (_e) { p = { error: t }; }
        if (!r.ok) throw new Error(p.error || r.statusText);
        return p;
      });
    });
  }
  var exportBtn = root.querySelector('[data-rmc-tenant-export]');
  if (exportBtn) {
    exportBtn.addEventListener('click', function () {
      exportBtn.disabled = true;
      post(cfg.api_export, { full: true })
        .then(function (d) {
          status('Export ready (' + (d.student_export_count || 0) + ' students). Reload to download.', 'success');
        })
        .catch(function (e) { status(e.message, 'danger'); })
        .finally(function () { exportBtn.disabled = false; });
    });
  }
  var reqBtn = root.querySelector('[data-rmc-tenant-request-closure]');
  if (reqBtn) {
    reqBtn.addEventListener('click', function () {
      var ack = root.querySelector('[data-rmc-tenant-ack]');
      if (!ack || !ack.checked) {
        status(operatorOnly
          ? 'Acknowledge operator approval and grace period first.'
          : 'Acknowledge irreversible closure first.', 'warning');
        return;
      }
      var confirmMsg = operatorOnly
        ? 'Submit offboarding request to platform operators? Your school stays active until approved.'
        : 'Request account closure and schedule deletion after the grace period?';
      if (!window.confirm(confirmMsg)) return;
      post(cfg.api_request, { acknowledge: true })
        .then(function (d) {
          if (operatorOnly || d.mode === 'operator_request') {
            status('Offboarding request submitted. Platform operators will review it.', 'success');
            var st = root.querySelector('[data-rmc-ss-status]');
            if (st) st.textContent = 'requested';
          } else {
            status('Closure scheduled for ' + (d.scheduled_purge_at || ''), 'success');
            var s = root.querySelector('[data-rmc-ss-scheduled]');
            if (s) s.textContent = d.scheduled_purge_at || '';
          }
        })
        .catch(function (e) { status(e.message, 'danger'); });
    });
  }
  var cancelBtn = root.querySelector('[data-rmc-tenant-cancel-closure]');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () {
      post(cfg.api_cancel, {})
        .then(function () {
          status(operatorOnly ? 'Offboarding request withdrawn.' : 'Scheduled closure cancelled.', 'success');
          var st = root.querySelector('[data-rmc-ss-status]');
          if (st) st.textContent = 'cancelled';
        })
        .catch(function (e) { status(e.message, 'danger'); });
    });
  }
})();
