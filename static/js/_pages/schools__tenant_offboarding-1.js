// Tenant 360 offboarding panel — control plane API wiring (v3.58.3)
(function () {
  'use strict';

  var panel = document.querySelector('[data-rmc-offboarding-panel]');
  if (!panel) return;

  var dataEl = document.getElementById('page-data-schools__tenant_offboarding-1');
  var cfg = {};
  if (dataEl && dataEl.textContent) {
    try {
      cfg = JSON.parse(dataEl.textContent);
    } catch (_e) {
      cfg = {};
    }
  }

  function readCookie(name) {
    var match = document.cookie.match(
      new RegExp('(?:^|; )' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '=([^;]*)')
    );
    return match ? decodeURIComponent(match[1]) : '';
  }

  function csrfToken() {
    var input = document.querySelector('[name=csrfmiddlewaretoken]');
    if (input && input.value) return input.value;
    return readCookie('csrftoken') || readCookie('rmc_manager_csrftoken') || '';
  }

  function htmlLoginHint(text) {
    if (!text || text.indexOf('<!doctype') === -1) return '';
    return ' Session may have expired — sign in again on manager.runmycampus.com.';
  }

  function statusEl() {
    return panel.querySelector('[data-rmc-offboarding-status]');
  }

  function showStatus(message, tone) {
    var el = statusEl();
    if (!el) return;
    el.textContent = message;
    el.className = 'alert alert-' + (tone || 'secondary') + ' small mt-2';
    el.classList.remove('d-none');
  }

  function apiPost(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        Accept: 'application/json',
      },
      body: JSON.stringify(body || {}),
    }).then(function (res) {
      return res.text().then(function (text) {
        var payload = null;
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch (_e) {
            payload = {
              ok: false,
              error: 'Unexpected response (not JSON).' + htmlLoginHint(text),
            };
          }
        }
        if (!res.ok) {
          var err =
            (payload && (payload.error || payload.detail)) ||
            res.statusText ||
            'Request failed';
          if (htmlLoginHint(text)) err += htmlLoginHint(text);
          throw new Error(err);
        }
        return payload || {};
      });
    });
  }

  var INVENTORY_PAGE = 50;
  var inventoryRows = [];
  var inventoryPage = 1;

  function renderInventoryPage() {
    var tableWrap = panel.querySelector('[data-rmc-inventory-table]');
    var body = panel.querySelector('[data-rmc-inventory-body]');
    var pager = panel.querySelector('[data-rmc-inventory-pager]');
    if (!tableWrap || !body) return;
    tableWrap.classList.remove('d-none');
    body.textContent = '';
    var start = (inventoryPage - 1) * INVENTORY_PAGE;
    var slice = inventoryRows.slice(start, start + INVENTORY_PAGE);
    slice.forEach(function (row) {
      var tr = document.createElement('tr');
      var tdM = document.createElement('td');
      var tdC = document.createElement('td');
      tdM.textContent = row[0];
      tdC.textContent = String(row[1]);
      tr.appendChild(tdM);
      tr.appendChild(tdC);
      body.appendChild(tr);
    });
    if (!pager) return;
    var pages = Math.max(1, Math.ceil(inventoryRows.length / INVENTORY_PAGE));
    if (pages <= 1) {
      pager.classList.add('d-none');
      return;
    }
    pager.classList.remove('d-none');
    pager.textContent = '';
    var prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'btn btn-sm btn-outline-secondary me-1';
    prev.textContent = 'Previous';
    prev.disabled = inventoryPage <= 1;
    prev.addEventListener('click', function () {
      inventoryPage = Math.max(1, inventoryPage - 1);
      renderInventoryPage();
    });
    var label = document.createElement('span');
    label.className = 'small text-secondary mx-1';
    label.textContent = 'Page ' + inventoryPage + ' / ' + pages;
    var next = document.createElement('button');
    next.type = 'button';
    next.className = 'btn btn-sm btn-outline-secondary ms-1';
    next.textContent = 'Next';
    next.disabled = inventoryPage >= pages;
    next.addEventListener('click', function () {
      inventoryPage = Math.min(pages, inventoryPage + 1);
      renderInventoryPage();
    });
    pager.appendChild(prev);
    pager.appendChild(label);
    pager.appendChild(next);
  }

  function dualApprovedForPurge() {
    if (!cfg.dual_approval_required) return false;
    if (cfg.dual_approved) return true;
    var second = panel.querySelector('[data-rmc-dual-second]');
    return !!(second && second.checked);
  }

  function purgePayload(dryRun) {
    var slugInput = panel.querySelector('[data-rmc-confirm-slug]');
    var ack = panel.querySelector('[data-rmc-purge-ack]');
    var force = panel.querySelector('[data-rmc-force-provisioning]');
    return {
      confirm_slug: slugInput ? slugInput.value.trim() : '',
      dry_run: !!dryRun,
      force_provisioning: force ? force.checked : false,
      dual_approved: dualApprovedForPurge(),
      irreversible_ack: ack ? ack.checked : false,
    };
  }

  function updateApplyEnabled() {
    var applyBtn = panel.querySelector('[data-rmc-purge-apply]');
    var slugInput = panel.querySelector('[data-rmc-confirm-slug]');
    var ack = panel.querySelector('[data-rmc-purge-ack]');
    if (!applyBtn) return;
    var slugOk =
      slugInput && slugInput.value.trim() === (cfg.school_slug || '');
    var ackOk = ack && ack.checked;
    var dualOk = !cfg.dual_approval_required || dualApprovedForPurge();
    applyBtn.disabled = !(slugOk && ackOk && dualOk);
  }

  var slugInput = panel.querySelector('[data-rmc-confirm-slug]');
  var ack = panel.querySelector('[data-rmc-purge-ack]');
  if (slugInput) slugInput.addEventListener('input', updateApplyEnabled);
  if (ack) ack.addEventListener('change', updateApplyEnabled);
  var dualSecond = panel.querySelector('[data-rmc-dual-second]');
  if (dualSecond) dualSecond.addEventListener('change', updateApplyEnabled);

  var dualPrimaryBtn = panel.querySelector('[data-rmc-dual-primary]');
  if (dualPrimaryBtn && cfg.api_dual_approve) {
    dualPrimaryBtn.addEventListener('click', function () {
      dualPrimaryBtn.disabled = true;
      apiPost(cfg.api_dual_approve, { step: 'primary' })
        .then(function () {
          showStatus('First operator approval recorded. Reload for second step.', 'success');
          window.setTimeout(function () {
            window.location.reload();
          }, 800);
        })
        .catch(function (err) {
          showStatus(err.message, 'danger');
          dualPrimaryBtn.disabled = false;
        });
    });
  }

  var exportBtn = panel.querySelector('[data-rmc-offboarding-export]');
  if (exportBtn) {
    exportBtn.addEventListener('click', function () {
      exportBtn.disabled = true;
      showStatus('Export started…', 'info');
      apiPost(cfg.api_export, { full: true })
        .then(function (data) {
          var out = panel.querySelector('[data-rmc-export-result]');
          if (out) {
            out.textContent =
              'Export complete: ' +
              (data.student_export_count || 0) +
              ' students — ' +
              (data.export_zip_path || '');
            out.classList.remove('d-none');
          }
          showStatus('Portability export finished.', 'success');
        })
        .catch(function (err) {
          showStatus(err.message || 'Export failed', 'danger');
        })
        .finally(function () {
          exportBtn.disabled = false;
        });
    });
  }

  var deactivateBtn = panel.querySelector('[data-rmc-offboarding-deactivate]');
  if (deactivateBtn) {
    deactivateBtn.addEventListener('click', function () {
      deactivateBtn.disabled = true;
      apiPost(cfg.api_deactivate, {})
        .then(function () {
          showStatus('Tenant deactivated for wind-down.', 'success');
        })
        .catch(function (err) {
          showStatus(err.message || 'Deactivate failed', 'danger');
        })
        .finally(function () {
          deactivateBtn.disabled = false;
        });
    });
  }

  function saveHold(until) {
    return apiPost(cfg.api_hold, { hold_until: until || null }).then(function () {
      showStatus(until ? 'Legal hold saved.' : 'Legal hold cleared.', 'success');
    });
  }

  var holdSave = panel.querySelector('[data-rmc-offboarding-hold-save]');
  if (holdSave) {
    holdSave.addEventListener('click', function () {
      var input = panel.querySelector('[data-rmc-hold-until]');
      saveHold(input ? input.value : null).catch(function (err) {
        showStatus(err.message, 'danger');
      });
    });
  }
  var holdClear = panel.querySelector('[data-rmc-offboarding-hold-clear]');
  if (holdClear) {
    holdClear.addEventListener('click', function () {
      var input = panel.querySelector('[data-rmc-hold-until]');
      if (input) input.value = '';
      saveHold(null).catch(function (err) {
        showStatus(err.message, 'danger');
      });
    });
  }

  var dryBtn = panel.querySelector('[data-rmc-purge-dry-run]');
  if (dryBtn) {
    dryBtn.addEventListener('click', function () {
      dryBtn.disabled = true;
      apiPost(cfg.api_purge, purgePayload(true))
        .then(function (data) {
          var preview = (data && data.preview) || {};
          inventoryRows = Object.keys(preview.inventory || {})
            .sort()
            .map(function (k) {
              return [k, preview.inventory[k]];
            });
          inventoryPage = 1;
          renderInventoryPage();
          showStatus(
            'Dry-run: ' + (preview.row_total || 0) + ' rows — manifest ' + (preview.manifest_path || ''),
            'info'
          );
        })
        .catch(function (err) {
          showStatus(err.message, 'danger');
        })
        .finally(function () {
          dryBtn.disabled = false;
        });
    });
  }

  var applyBtn = panel.querySelector('[data-rmc-purge-apply]');
  if (applyBtn) {
    applyBtn.addEventListener('click', function () {
      if (
        !window.confirm(
          'Permanent delete cannot be undone. Continue?'
        )
      ) {
        return;
      }
      applyBtn.disabled = true;
      apiPost(cfg.api_purge, purgePayload(false))
        .then(function (data) {
          var receipt = (data && data.receipt) || {};
          var box = panel.querySelector('[data-rmc-purge-receipt]');
          if (box) {
            box.textContent =
              'Deleted ' +
              (receipt.school_slug || '') +
              ' at ' +
              (receipt.deleted_at || '') +
              '. Manifest: ' +
              (receipt.manifest_path || '') +
              '. Schema dropped: ' +
              (receipt.schema_dropped || 'n/a');
            box.classList.remove('d-none');
          }
          showStatus('Permanent delete completed.', 'success');
        })
        .catch(function (err) {
          showStatus(err.message, 'danger');
          applyBtn.disabled = false;
          updateApplyEnabled();
        });
    });
  }

  var schedBtn = panel.querySelector('[data-rmc-offboarding-schedule]');
  if (schedBtn) {
    schedBtn.addEventListener('click', function () {
      var dateInput = panel.querySelector('[data-rmc-schedule-date]');
      var scheduled = dateInput ? dateInput.value : '';
      if (!scheduled) {
        showStatus('Pick a purge date.', 'warning');
        return;
      }
      apiPost(cfg.api_schedule, { scheduled_purge_at: scheduled })
        .then(function () {
          showStatus('Auto-purge scheduled for ' + scheduled, 'success');
        })
        .catch(function (e) {
          showStatus(e.message, 'danger');
        });
    });
  }

  updateApplyEnabled();

  var approveBtn = panel.querySelector('[data-rmc-approve-offboarding-request]');
  if (approveBtn && cfg.api_approve_request) {
    approveBtn.addEventListener('click', function () {
      if (!window.confirm('Approve tenant offboarding request and schedule wind-down?')) return;
      apiPost(cfg.api_approve_request, {})
        .then(function () {
          showStatus('Offboarding request approved.', 'success');
          window.setTimeout(function () { window.location.reload(); }, 1200);
        })
        .catch(function (e) { showStatus(e.message, 'danger'); });
    });
  }

  var rejectBtn = panel.querySelector('[data-rmc-reject-offboarding-request]');
  if (rejectBtn && cfg.api_reject_request) {
    rejectBtn.addEventListener('click', function () {
      var reason = window.prompt('Rejection reason (optional):') || '';
      apiPost(cfg.api_reject_request, { reason: reason })
        .then(function () {
          showStatus('Offboarding request rejected.', 'success');
          window.setTimeout(function () { window.location.reload(); }, 1200);
        })
        .catch(function (e) { showStatus(e.message, 'danger'); });
    });
  }

  var certBtn = panel.querySelector('[data-rmc-download-purge-certificate]');
  if (certBtn && cfg.api_purge_certificate) {
    certBtn.addEventListener('click', function () {
      fetch(cfg.api_purge_certificate, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (!data.ok || !data.deletion_certificate) {
            throw new Error((data && data.error) || 'No certificate');
          }
          var blob = new Blob([JSON.stringify(data.deletion_certificate, null, 2)], {
            type: 'application/json',
          });
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = (cfg.school_slug || 'tenant') + '-deletion-certificate.json';
          a.click();
          URL.revokeObjectURL(a.href);
          showStatus('Certificate downloaded.', 'success');
        })
        .catch(function (e) { showStatus(e.message, 'warning'); });
    });
  }
})();
