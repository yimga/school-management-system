// Offboarding queue — scheduled purge dry-run + operator apply (control plane)
(function () {
  'use strict';

  var dryBtn = document.querySelector('[data-rmc-run-scheduled-dry-run]');
  var applyBtn = document.querySelector('[data-rmc-run-scheduled-apply]');
  var out = document.querySelector('[data-rmc-scheduled-purge-result]');
  if (!out) return;

  var dataEl = document.getElementById('page-data-super_offboarding_queue-1');
  var cfg = {};
  if (dataEl && dataEl.textContent) {
    try {
      cfg = JSON.parse(dataEl.textContent);
    } catch (_e) {
      cfg = {};
    }
  }
  if (!cfg.api_run_scheduled) return;

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

  function runScheduled(opts) {
    var btn = opts.button;
    btn.disabled = true;
    out.classList.remove('d-none');
    out.textContent = opts.label + '…';
    return fetch(cfg.api_run_scheduled, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        Accept: 'application/json',
      },
      body: JSON.stringify(opts.body),
    })
      .then(function (res) {
        return res.text().then(function (text) {
          var payload = null;
          if (text) {
            try {
              payload = JSON.parse(text);
            } catch (_e) {
              throw new Error(
                'Unexpected response (not JSON).' + htmlLoginHint(text)
              );
            }
          }
          if (!res.ok) {
            var err =
              (payload && (payload.error || payload.detail || payload.hint)) ||
              res.statusText;
            if (htmlLoginHint(text)) err += htmlLoginHint(text);
            throw new Error(err);
          }
          return payload;
        });
      })
      .then(function (payload) {
        out.textContent = JSON.stringify(payload, null, 2);
        if (payload && payload.processed && payload.processed.some(function (e) {
          return e.purged;
        })) {
          window.setTimeout(function () {
            window.location.reload();
          }, 1500);
        }
      })
      .catch(function (err) {
        out.textContent = String(err && err.message ? err.message : err);
      })
      .finally(function () {
        btn.disabled = false;
      });
  }

  if (dryBtn) {
    dryBtn.addEventListener('click', function () {
      runScheduled({
        button: dryBtn,
        label: 'Running dry-run',
        body: { dry_run: true, limit: 10 },
      });
    });
  }

  if (applyBtn) {
    applyBtn.addEventListener('click', function () {
      var msg =
        'Apply purge for all schools due today? This permanently deletes tenant data.';
      if (!cfg.auto_purge_enabled) {
        msg +=
          ' Auto-purge is DISABLED — this is a one-time operator run (type purge-due-tenants to confirm).';
      }
      if (!window.confirm(msg)) return;
      var confirmText = 'purge-due-tenants';
      if (!cfg.auto_purge_enabled) {
        var typed = window.prompt(
          'Type purge-due-tenants to confirm permanent delete:'
        );
        if (typed !== confirmText) {
          out.classList.remove('d-none');
          out.textContent = 'Cancelled — confirmation phrase did not match.';
          return;
        }
      }
      runScheduled({
        button: applyBtn,
        label: 'Applying due purges',
        body: {
          dry_run: false,
          limit: 10,
          force_operator: true,
          confirm: confirmText,
        },
      });
    });
  }

  function postJson(url, body) {
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
            throw new Error('Unexpected response (not JSON).' + htmlLoginHint(text));
          }
        }
        if (!res.ok) {
          var err =
            (payload && (payload.error || payload.detail || payload.hint)) ||
            res.statusText;
          throw new Error(err);
        }
        return payload;
      });
    });
  }

  document.querySelectorAll('[data-rmc-approve-request]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.getAttribute('data-api-url');
      if (!url) return;
      if (!window.confirm('Approve offboarding request? School will wind down and purge will be scheduled.')) {
        return;
      }
      btn.disabled = true;
      postJson(url, {})
        .then(function () {
          window.location.reload();
        })
        .catch(function (err) {
          out.classList.remove('d-none');
          out.textContent = String(err && err.message ? err.message : err);
          btn.disabled = false;
        });
    });
  });

  document.querySelectorAll('[data-rmc-reject-request]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.getAttribute('data-api-url');
      if (!url) return;
      var reason = window.prompt('Rejection reason (optional):') || '';
      btn.disabled = true;
      postJson(url, { reason: reason })
        .then(function () {
          window.location.reload();
        })
        .catch(function (err) {
          out.classList.remove('d-none');
          out.textContent = String(err && err.message ? err.message : err);
          btn.disabled = false;
        });
    });
  });
})();
