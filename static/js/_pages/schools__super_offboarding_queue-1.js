// Offboarding queue — scheduled purge dry-run (control plane)
(function () {
  'use strict';

  var btn = document.querySelector('[data-rmc-run-scheduled-dry-run]');
  var out = document.querySelector('[data-rmc-scheduled-purge-result]');
  if (!btn || !out) return;

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

  function csrfToken() {
    var input = document.querySelector('[name=csrfmiddlewaretoken]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  btn.addEventListener('click', function () {
    btn.disabled = true;
    out.classList.remove('d-none');
    out.textContent = 'Running dry-run…';
    fetch(cfg.api_run_scheduled, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        Accept: 'application/json',
      },
      body: JSON.stringify({ dry_run: true, limit: 10 }),
    })
      .then(function (res) {
        return res.text().then(function (text) {
          var payload = null;
          if (text) {
            try {
              payload = JSON.parse(text);
            } catch (_e) {
              payload = { raw: text.slice(0, 2000) };
            }
          }
          if (!res.ok) {
            throw new Error(
              (payload && (payload.error || payload.detail)) || res.statusText
            );
          }
          return payload;
        });
      })
      .then(function (payload) {
        out.textContent = JSON.stringify(payload, null, 2);
      })
      .catch(function (err) {
        out.textContent = String(err && err.message ? err.message : err);
      })
      .finally(function () {
        btn.disabled = false;
      });
  });
})();
