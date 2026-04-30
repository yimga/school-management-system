/**
 * Offline outbox: localStorage (legacy) + IndexedDB (Dexie) when SMSOfflineDB loads.
 * POSTs to /portal/api/offline/enqueue/ then /portal/api/offline/process/ on reconnect.
 * See apps.platform_runtime.offline_queue (server queue + conflict resolution).
 */
(function () {
  var LS_KEY = 'rmc-offline-outbox-v1';
  var FLUSHING = false;

  function getConfig() {
    return window.SMS_OFFLINE_CONFIG || {};
  }

  function getCookie(name) {
    var cookies = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name + '=') === 0) return decodeURIComponent(c.substring(name.length + 1));
    }
    return '';
  }

  function readOutboxLS() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) return [];
      var j = JSON.parse(raw);
      return Array.isArray(j) ? j : [];
    } catch (e) {
      return [];
    }
  }

  function writeOutboxLS(rows) {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(rows));
    } catch (e) { /* quota */ }
  }

  function countLocal() {
    var n = readOutboxLS().length;
    return n;
  }

  function updateBar() {
    var bar = document.getElementById('rmc-offline-sync-bar');
    if (!bar) return;
    var localN = countLocal();
    var idbN = 0;
    if (window.SMSOfflineDB && window.SMSOfflineDB.outboxPending) {
      /* sync count: avoid blocking — bar updates on next event */
    }
    var pending = parseInt(bar.getAttribute('data-server-pending') || '0', 10) || 0;
    var failed = parseInt(bar.getAttribute('data-server-failed') || '0', 10) || 0;
    var conflicts = parseInt(bar.getAttribute('data-server-conflicts') || '0', 10) || 0;
    var label = bar.querySelector('[data-rmc-offline-label]');
    var badge = bar.querySelector('[data-rmc-local-badge]');
    var badgeTotal = bar.querySelector('[data-rmc-queue-total]');
    var retry = bar.querySelector('[data-rmc-offline-retry]');
    var conflictLink = bar.querySelector('[data-rmc-conflicts-link]');
    var online = navigator.onLine;
    var totalQueue = localN + pending + failed;

    var show = !online || localN > 0 || pending > 0 || failed > 0 || conflicts > 0;
    bar.classList.toggle('d-none', !show);

    if (label) {
      if (!online) {
        label.textContent = 'Offline — changes stay on this device until you reconnect.';
      } else if (localN > 0 || pending > 0) {
        label.textContent = 'Sync pending — ' + (localN + pending) + ' item(s) in queue.';
      } else if (failed > 0) {
        label.textContent = 'Some items need a retry.';
      } else if (conflicts > 0) {
        label.textContent = 'Conflicts need your choice.';
      } else {
        label.textContent = 'All changes synced.';
      }
    }
    if (badge) {
      badge.classList.toggle('d-none', localN === 0);
      badge.textContent = localN + ' local';
    }
    if (badgeTotal) {
      badgeTotal.classList.toggle('d-none', totalQueue === 0 && conflicts === 0);
      badgeTotal.textContent = String(totalQueue + conflicts);
    }
    if (retry) {
      retry.classList.toggle('d-none', !(failed > 0 || (localN > 0 && online)));
      retry.onclick = function () {
        flushIfOnline();
      };
    }
    if (conflictLink) {
      conflictLink.classList.toggle('d-none', conflicts === 0);
    }
  }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, json: j }; }); });
  }

  /**
   * Push one logical action to the server queue (idempotent when idempotency_key set).
   */
  function enqueueAction(payload) {
    if (!payload || typeof payload !== 'object') return;
    var actionType = payload.action_type || payload.type;
    if (!actionType) return;

    var row = {
      id: 'c-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9),
      payload: payload,
      action_type: actionType,
      ts: Date.now(),
      synced: 0,
      idempotency_key: payload.idempotency_key || payload.client_offline_id || '',
    };

    if (window.SMSOfflineDB && typeof window.SMSOfflineDB.outboxEnqueue === 'function') {
      window.SMSOfflineDB.outboxEnqueue(row).then(function () {
        updateBar();
        flushIfOnline();
      });
    } else {
      var rows = readOutboxLS();
      rows.push({ id: row.id, payload: payload, ts: new Date().toISOString() });
      writeOutboxLS(rows);
      updateBar();
      flushIfOnline();
    }
  }

  function flushRowsFromLS() {
    var cfg = getConfig();
    var enqueueUrl = cfg.offlineEnqueueUrl || cfg.offline_enqueue_url;
    var processUrl = cfg.offlineProcessUrl || cfg.offline_process_url;
    if (!enqueueUrl) return Promise.resolve({ ok: false, reason: 'no_enqueue_url' });

    var rows = readOutboxLS();
    if (!rows.length) return Promise.resolve({ ok: true, drained: 0 });

    var remaining = [];
    var synced = 0;
    var chain = Promise.resolve();
    rows.forEach(function (entry) {
      chain = chain.then(function () {
        var p = entry.payload || {};
        var actionType = p.action_type || p.type;
        if (!actionType) {
          remaining.push(entry);
          return;
        }
        return postJson(enqueueUrl, {
          action_type: actionType,
          payload: p.payload !== undefined ? p.payload : p,
          idempotency_key: p.idempotency_key || p.client_offline_id || entry.id || '',
        }).then(function (res) {
          if (res.ok && res.json && res.json.ok) synced += 1;
          else remaining.push(entry);
        });
      });
    });
    return chain.then(function () {
      writeOutboxLS(remaining);
      if (processUrl && synced > 0) {
        return postJson(processUrl, {}).then(function () { return { ok: true, drained: synced }; });
      }
      return { ok: true, drained: synced };
    });
  }

  function flushRowsFromIdb() {
    var cfg = getConfig();
    var enqueueUrl = cfg.offlineEnqueueUrl || cfg.offline_enqueue_url;
    var processUrl = cfg.offlineProcessUrl || cfg.offline_process_url;
    if (!enqueueUrl || !window.SMSOfflineDB || !window.SMSOfflineDB.outboxPending) {
      return flushRowsFromLS();
    }
    return window.SMSOfflineDB.outboxPending().then(function (rows) {
      if (!rows || !rows.length) return flushRowsFromLS();
      var synced = 0;
      var seq = Promise.resolve();
      rows.forEach(function (entry) {
        seq = seq.then(function () {
          var p = entry.payload || {};
          var actionType = entry.action_type || p.action_type || p.type;
          if (!actionType) return;
          return postJson(enqueueUrl, {
            action_type: actionType,
            payload: typeof p.payload === 'object' ? p.payload : p,
            idempotency_key: p.idempotency_key || p.client_offline_id || String(entry.id || ''),
          }).then(function (res) {
            if (res.ok && res.json && res.json.ok) {
              synced += 1;
              return window.SMSOfflineDB.outboxDelete(entry.id);
            }
          });
        });
      });
      return seq.then(function () {
        return flushRowsFromLS().then(function (lsRes) {
          if (processUrl && synced > 0) {
            return postJson(processUrl, {}).then(function () {
              return { ok: true, drained: synced + (lsRes.drained || 0) };
            });
          }
          return lsRes;
        });
      });
    });
  }

  function flushIfOnline() {
    if (!navigator.onLine || FLUSHING) return;
    var cfg = getConfig();
    if (!cfg.offlineEnqueueUrl && !cfg.offline_enqueue_url) return;
    FLUSHING = true;
    flushRowsFromIdb()
      .catch(function () {})
      .then(function () {
        FLUSHING = false;
        updateBar();
      });
  }

  window.rmcOfflineEnqueue = enqueueAction;
  window.rmcOfflineDrainLocal = function () {
    writeOutboxLS([]);
    if (window.SMSOfflineDB && window.SMSOfflineDB.outboxPending) {
      window.SMSOfflineDB.outboxPending().then(function (rows) {
        if (!rows || !rows.length) return;
        var d = Promise.resolve();
        rows.forEach(function (r) {
          d = d.then(function () { return window.SMSOfflineDB.outboxDelete(r.id); });
        });
        return d;
      });
    }
    updateBar();
  };
  window.rmcOfflineFlushNow = flushIfOnline;

  window.addEventListener('online', function () {
    updateBar();
    flushIfOnline();
  });
  window.addEventListener('offline', updateBar);
  document.addEventListener('DOMContentLoaded', function () {
    updateBar();
    flushIfOnline();
    setInterval(function () {
      if (navigator.onLine) flushIfOnline();
    }, 45000);
    if (window.SMSOfflineDB && window.SMSOfflineDB.outboxPending) {
      window.SMSOfflineDB.outboxPending().then(function (rows) {
        var extra = rows ? rows.length : 0;
        if (extra > 0) updateBar();
      });
    }
  });
})();
