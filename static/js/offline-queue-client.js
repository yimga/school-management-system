/**
 * Offline outbox: localStorage (legacy) + IndexedDB (Dexie) when SMSOfflineDB loads.
 * POSTs to /portal/api/offline/enqueue/ then /portal/api/offline/process/ on reconnect.
 * See apps.platform_runtime.offline_queue (server queue + conflict resolution).
 */
(function () {
  var LS_KEY = 'rmc-offline-outbox-v1';
  var FLUSHING = false;
  var globalRoot =
    typeof globalThis !== 'undefined'
      ? globalThis
      : typeof window !== 'undefined'
        ? window
        : {};

  function getConfig() {
    return window.SMS_OFFLINE_CONFIG || {};
  }

  /** The logged-in user id (server-populated in SMS_OFFLINE_CONFIG.currentUserId). */
  function currentUserId() {
    try {
      var v = getConfig().currentUserId;
      return v == null ? '' : String(v);
    } catch (e) {
      return '';
    }
  }

  /**
   * Cross-user flush guard (shared-device safety). A queued row may only sync
   * under the user who created it: on a shared device this stops User A's
   * unsynced attendance / grades / payment proofs from being POSTed under
   * User B's session after a logout + login. A row is held back ONLY when we
   * positively know the current user differs from the row's stamped owner —
   * legacy rows with no owner still flush (back-compat), and when the current
   * user is unknown (no config) we fall back to the prior behaviour rather than
   * stranding work.
   */
  function rowBlockedForCurrentUser(entry) {
    if (!entry) return false;
    var owner = entry.owner || (entry.payload && entry.payload.__owner) || '';
    var cur = currentUserId();
    return !!(owner && cur && String(owner) !== cur);
  }

  var CAUSAL_COUNTER_KEY = 'rmc_offline_lamport_v1';
  var CAUSAL_REPLICA_KEY = 'rmc_offline_replica_v1';

  function causalReplicaId() {
    try {
      var existing = localStorage.getItem(CAUSAL_REPLICA_KEY);
      if (existing) return existing;
      var created = (window.crypto && typeof window.crypto.randomUUID === 'function')
        ? window.crypto.randomUUID()
        : 'browser-' + Date.now() + '-' + Math.random().toString(16).slice(2);
      localStorage.setItem(CAUSAL_REPLICA_KEY, created);
      return created;
    } catch (e) {
      return 'browser-session';
    }
  }

  function nextCausalClock() {
    var logical = 1;
    try {
      logical = Math.max(
        0,
        Math.trunc(Number(localStorage.getItem(CAUSAL_COUNTER_KEY)) || 0)
      ) + 1;
      localStorage.setItem(CAUSAL_COUNTER_KEY, String(logical));
    } catch (e) { /* storage unavailable */ }
    return '0:' + logical + ':' + causalReplicaId();
  }

  /** Canonical offline event_envelope (batch 1532 — queued sync, not CRDT). */
  function buildOfflineEnvelope(opts) {
    var o = opts || {};
    return {
      entity: o.entity || '',
      entity_id: String(o.entity_id || ''),
      op: o.op || 'upsert',
      attribute_key: o.attribute_key || '',
      attribute_value: o.attribute_value,
      deterministic_timestamp: o.deterministic_timestamp || new Date().toISOString(),
      client_id: o.client_id || '',
      causal_clock: o.causal_clock || nextCausalClock(),
    };
  }

  function mergeEnvelopePayload(actionType, payload) {
    if (!payload || payload.entity) return payload;
    var at = actionType || payload.action_type || '';
    if (at === 'attendance.mark' || at === 'attendance') {
      return buildOfflineEnvelope({
        entity: 'attendance_record',
        entity_id: String(payload.classroom_id || '') + ':' + String(payload.date || ''),
        attribute_key: 'status',
        attribute_value: payload,
        client_id: payload.idempotency_key || payload.client_offline_id || '',
      });
    }
    return payload;
  }

  function getCookie(name) {
    var cookies = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name + '=') === 0) return decodeURIComponent(c.substring(name.length + 1));
    }
    return '';
  }

  // CSRF token for POSTs. Read the DOM first: with CSRF_COOKIE_HTTPONLY=True the
  // csrftoken cookie is invisible to JS, so getCookie('csrftoken') returns '' and
  // the server rejects the empty header ("incorrect length"). The rendered
  // csrfmiddlewaretoken input / <meta name="csrf-token"> always carry a valid
  // token; the cookie is only a last resort for pages without either.
  function csrfToken() {
    var input = document.querySelector('input[name=csrfmiddlewaretoken]');
    if (input && input.value) { return input.value; }
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.getAttribute('content')) { return meta.getAttribute('content'); }
    return getCookie('csrftoken');
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
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, json: j }; }); });
  }

  /**
   * Push one logical action to the server queue (idempotent when idempotency_key set).
   */
  var OFFLINE_ACTION_CAPABILITY = {
    'attendance.mark': 'attendance.mark',
    attendance: 'attendance.mark',
    'grade.submit': 'grade.submit',
    grading: 'grade.submit',
    'payment.proof_upload': 'finance.manage',
    'payment_receipt': 'finance.manage',
  };

  function offlineActionAllowed(actionType) {
    var code = OFFLINE_ACTION_CAPABILITY[actionType];
    if (!code) return true;
    if (!globalRoot.RMCIamSnapshot || typeof globalRoot.RMCIamSnapshot.hasCapability !== 'function') {
      return true;
    }
    return globalRoot.RMCIamSnapshot.hasCapability(code);
  }

  function enqueueAction(payload) {
    if (!payload || typeof payload !== 'object') return;
    var actionType = payload.action_type || payload.type;
    if (!actionType) return;
    if (!offlineActionAllowed(actionType)) {
      return;
    }

    var owner = currentUserId();
    var row = {
      id: 'c-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9),
      payload: payload,
      action_type: actionType,
      ts: Date.now(),
      synced: 0,
      owner: owner,
      idempotency_key: payload.idempotency_key || payload.client_offline_id || '',
    };

    if (window.SMSOfflineDB && typeof window.SMSOfflineDB.outboxEnqueue === 'function') {
      window.SMSOfflineDB.outboxEnqueue(row).then(function () {
        updateBar();
        flushIfOnline();
      });
    } else {
      var rows = readOutboxLS();
      rows.push({ id: row.id, payload: payload, ts: new Date().toISOString(), owner: owner });
      writeOutboxLS(rows);
      updateBar();
      flushIfOnline();
    }
  }

  function applyServerConflictCount(summary) {
    if (!summary || typeof summary.conflicts !== 'number') return;
    var bar = document.getElementById('rmc-offline-sync-bar');
    if (bar) {
      bar.setAttribute('data-server-conflicts', String(summary.conflicts));
    }
    var cfg = getConfig();
    var conflictsUrl = cfg.offlineConflictsUrl || cfg.offline_conflicts_url;
    if (summary.conflicts > 0) {
      try {
        document.dispatchEvent(new CustomEvent('rmc-offline-conflicts-updated', {
          bubbles: true,
          detail: { count: summary.conflicts, url: conflictsUrl || '' }
        }));
      } catch (e) {}
    }
  }

  function runProcessQueue() {
    var cfg = getConfig();
    var processUrl = cfg.offlineProcessUrl || cfg.offline_process_url;
    if (!processUrl) return Promise.resolve(null);
    return postJson(processUrl, {}).then(function (res) {
      if (res.ok && res.json) applyServerConflictCount(res.json);
      return res;
    });
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
        if (rowBlockedForCurrentUser(entry)) {
          // Belongs to a different user — keep it queued for when they return.
          remaining.push(entry);
          return;
        }
        var p = entry.payload || {};
        var actionType = p.action_type || p.type;
        if (!actionType) {
          remaining.push(entry);
          return;
        }
        var rawPayload = p.payload !== undefined ? p.payload : p;
        return postJson(enqueueUrl, {
          action_type: actionType,
          payload: mergeEnvelopePayload(actionType, rawPayload),
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
        return runProcessQueue().then(function () { return { ok: true, drained: synced }; });
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
          if (rowBlockedForCurrentUser(entry)) {
            // Different user's row — leave it in IndexedDB until they return.
            return;
          }
          var p = entry.payload || {};
          var actionType = entry.action_type || p.action_type || p.type;
          if (!actionType) return;
          var idbPayload = typeof p.payload === 'object' ? p.payload : p;
          return postJson(enqueueUrl, {
            action_type: actionType,
            payload: mergeEnvelopePayload(actionType, idbPayload),
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
            return runProcessQueue().then(function () {
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

  // Best-effort flush BEFORE logout: drain this user's own queue to the server
  // while they are still authenticated and (hopefully) online, so a shared
  // device hands off with as little pending work as possible. Non-blocking and
  // never preventDefault — logout proceeds regardless. The owner-stamp guard
  // (rowBlockedForCurrentUser) is the real safety net for anything that does
  // not drain in time (e.g. offline at logout).
  function wireLogoutFlush() {
    document.addEventListener(
      'click',
      function (ev) {
        var t = ev.target;
        if (!t || typeof t.closest !== 'function') return;
        var hit = t.closest(
          'a[href*="/logout"], form[action*="/logout"] [type="submit"], [data-rmc-logout]'
        );
        if (hit) {
          try { flushIfOnline(); } catch (e) { /* never block logout */ }
        }
      },
      true
    );
  }

  function boot() {
    updateBar();
    flushIfOnline();
    wireLogoutFlush();
    setInterval(function () {
      if (navigator.onLine) flushIfOnline();
    }, 45000);
    if (window.SMSOfflineDB && window.SMSOfflineDB.outboxPending) {
      window.SMSOfflineDB.outboxPending().then(function (rows) {
        var extra = rows ? rows.length : 0;
        if (extra > 0) updateBar();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
