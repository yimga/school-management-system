/**
 * Offline outbox: localStorage (legacy) + IndexedDB (Dexie) when SMSOfflineDB loads.
 * POSTs to /portal/api/offline/enqueue/ then /portal/api/offline/process/ on reconnect.
 * See apps.platform_runtime.offline_queue (server queue + conflict resolution).
 */
(function () {
  var LS_KEY = 'rmc-offline-outbox-v1';
  var FLUSHING = false;

  /**
   * OUTBOX CAPACITY + EVICTION POLICY  (batch: globalization 0.4)
   * -------------------------------------------------------------
   * The localStorage rail is the fallback outbox for devices without
   * IndexedDB. localStorage is a hard-capped, shared, ~5MB-per-origin
   * store. A teacher on a 2G line can be offline for DAYS, so this queue
   * can genuinely grow until the store refuses the write.
   *
   * POLICY: REFUSE-NEW. At capacity we reject the INCOMING write and say
   * so loudly; we never evict an older unsynced row to make room.
   * Rationale: an old unsynced row is work the user was ALREADY told was
   * saved — dropping it is silent data loss after the fact, with nobody
   * watching. A new row can be refused in front of the user, who is
   * standing right there and can still act (reconnect and sync, free
   * space, or write it on paper). Loud refusal beats silent deletion.
   *
   * Two ceilings, whichever binds first:
   *   MAX_OUTBOX_ROWS  — bounds the flush loop (one POST per row).
   *   MAX_OUTBOX_CHARS — keeps us well under the origin quota so other
   *                      offline subsystems (drafts, WAL, caches) still
   *                      have room; localStorage quotas are counted in
   *                      UTF-16 code units, which is what String.length
   *                      returns.
   * BACK_PRESSURE_RATIO — we warn the user BEFORE the queue is full, so
   * they stop doing work they are about to lose rather than finding out
   * at the moment of refusal.
   */
  var MAX_OUTBOX_ROWS = 2000;
  var MAX_OUTBOX_CHARS = 2000000;
  var BACK_PRESSURE_RATIO = 0.8;
  var STORAGE_ALERT_ID = 'rmc-offline-storage-alert';
  var LAST_STORAGE_ALERT = '';

  function isQuotaError(err) {
    if (!err) return false;
    var name = err.name || '';
    return (
      name === 'QuotaExceededError' ||
      name === 'NS_ERROR_DOM_QUOTA_REACHED' ||
      err.code === 22 ||
      err.code === 1014
    );
  }

  /**
   * User-visible storage alarm. Deliberately NOT a console line and NOT a
   * transient toast: when a teacher's work was refused they must be able
   * to read it after the fact, so the banner persists until dismissed.
   * Rendered with inline styles + role="alert" so it works on any page,
   * with no CSS bundle and no toast library present. Also re-broadcast as
   * a DOM event so producer scripts (rmc-offline-portal-forms.js et al.)
   * can suppress their own "Saved on this device" toast.
   */
  function emitStorageAlert(level, message) {
    try {
      document.dispatchEvent(
        new CustomEvent('rmc-offline-storage-alert', {
          bubbles: true,
          detail: { level: level, message: message },
        })
      );
    } catch (e) { /* CustomEvent unsupported — banner below still runs */ }
    try {
      if (level === 'error' && typeof console !== 'undefined' && console.error) {
        console.error('[rmc-offline] ' + message);
      }
    } catch (e) { /* no console */ }
    try {
      if (!document.body) return;
      var host = document.getElementById(STORAGE_ALERT_ID);
      if (!host) {
        host = document.createElement('div');
        host.id = STORAGE_ALERT_ID;
        host.setAttribute('role', 'alert');
        host.setAttribute('aria-live', 'assertive');
        host.style.cssText =
          'position:fixed;left:0;right:0;top:0;z-index:2147483000;padding:12px 16px;' +
          'font:600 14px/1.4 system-ui,sans-serif;text-align:left;';
        var text = document.createElement('span');
        text.setAttribute('data-rmc-storage-alert-text', '');
        host.appendChild(text);
        var close = document.createElement('button');
        close.type = 'button';
        close.setAttribute('data-rmc-storage-alert-dismiss', '');
        close.textContent = 'Dismiss';
        close.style.cssText =
          'margin-left:12px;border:1px solid currentColor;background:transparent;' +
          'color:inherit;border-radius:4px;padding:2px 8px;cursor:pointer;';
        close.addEventListener('click', function () {
          if (host.parentNode) host.parentNode.removeChild(host);
          LAST_STORAGE_ALERT = '';
        });
        host.appendChild(close);
        document.body.appendChild(host);
      }
      host.setAttribute('data-rmc-storage-alert-level', level);
      host.style.background = level === 'error' ? '#b00020' : '#8a6100';
      host.style.color = '#fff';
      var span = host.querySelector('[data-rmc-storage-alert-text]');
      if (span) span.textContent = message;
      LAST_STORAGE_ALERT = level + ':' + message;
    } catch (e) { /* DOM unavailable — the event above already fired */ }
  }

  function warnStorageOnce(message) {
    // Back-pressure repeats on every enqueue; only repaint when it changes
    // so we do not thrash the DOM while a teacher marks a whole register.
    if (LAST_STORAGE_ALERT === 'warning:' + message) return;
    emitStorageAlert('warning', message);
  }
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

  /**
   * Persist the outbox. Returns { ok, reason } — NEVER swallows a failed
   * write. A silent failure here is the worst bug this file can have: the
   * UI toasts "Saved on this device" while the day's work never landed.
   *
   * We also read the value back: some storage implementations (Safari
   * private mode, quota-throttled WebViews) accept setItem without
   * throwing and then persist nothing. setItem returning is NOT proof the
   * write landed — probe the effect.
   */
  function writeOutboxLS(rows, preSerialized) {
    var serialized = preSerialized;
    if (typeof serialized !== 'string') {
      try {
        serialized = JSON.stringify(rows);
      } catch (e) {
        return { ok: false, reason: 'serialize_failed', error: e };
      }
    }
    try {
      localStorage.setItem(LS_KEY, serialized);
    } catch (e) {
      return {
        ok: false,
        reason: isQuotaError(e) ? 'quota_exceeded' : 'storage_unavailable',
        error: e,
      };
    }
    try {
      if (localStorage.getItem(LS_KEY) !== serialized) {
        return { ok: false, reason: 'write_not_persisted' };
      }
    } catch (e) {
      return { ok: false, reason: 'storage_unavailable', error: e };
    }
    return { ok: true, reason: '' };
  }

  /**
   * Capacity gate for ONE new row. Returns { ok, warn, reason, rows, chars,
   * serialized }. ok === false means the queue is full and the new row must
   * be refused (see REFUSE-NEW policy at the top of this file). `serialized`
   * is handed to writeOutboxLS so the hot path stringifies the outbox once,
   * not twice.
   */
  function capacityForNewRow(rows, candidate) {
    var serialized = '';
    try {
      serialized = JSON.stringify(rows.concat([candidate]));
    } catch (e) {
      return { ok: false, warn: false, reason: 'serialize_failed', rows: rows.length, chars: 0 };
    }
    var chars = serialized.length;
    var nextRows = rows.length + 1;
    if (nextRows > MAX_OUTBOX_ROWS) {
      return { ok: false, warn: true, reason: 'row_cap', rows: rows.length, chars: chars };
    }
    if (chars > MAX_OUTBOX_CHARS) {
      return { ok: false, warn: true, reason: 'byte_cap', rows: rows.length, chars: chars };
    }
    var warn =
      nextRows >= Math.floor(MAX_OUTBOX_ROWS * BACK_PRESSURE_RATIO) ||
      chars >= Math.floor(MAX_OUTBOX_CHARS * BACK_PRESSURE_RATIO);
    return {
      ok: true,
      warn: warn,
      reason: '',
      rows: nextRows,
      chars: chars,
      serialized: serialized,
    };
  }

  function outboxFullMessage(cap) {
    return (
      'NOT SAVED — the offline queue on this device is full (' +
      cap.rows +
      ' item(s) still waiting to sync). Your latest entry was refused so ' +
      'that earlier unsynced work is not lost. Reconnect and sync before ' +
      'entering more.'
    );
  }

  function writeFailedMessage(reason) {
    var why =
      reason === 'quota_exceeded'
        ? 'this device has run out of storage'
        : 'this device refused to store it';
    return (
      'NOT SAVED — your last entry could not be stored offline because ' +
      why +
      '. Do not close this page: reconnect and save again, or record it ' +
      'on paper.'
    );
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

  /**
   * Enqueue one action. ALWAYS returns a result object:
   *   { ok: true,  storage: 'indexeddb'|'localstorage', id, settled? }
   *   { ok: false, reason: '...' }
   * Callers MUST NOT report "saved" without checking `ok` — the whole
   * point of this rail is that the user is offline and has no other
   * confirmation that their work survived.
   */
  function enqueueAction(payload) {
    if (!payload || typeof payload !== 'object') return { ok: false, reason: 'invalid_payload' };
    var actionType = payload.action_type || payload.type;
    if (!actionType) return { ok: false, reason: 'missing_action_type' };
    if (!offlineActionAllowed(actionType)) {
      // Capability-denied drops are reported to the caller (ok:false) but
      // deliberately raise no storage banner: this is an authorization
      // decision, not a storage failure.
      return { ok: false, reason: 'capability_denied' };
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
      // IndexedDB writes are async, so `ok` here is "accepted", not
      // "durable". `settled` resolves to the durable result; a rejection
      // raises the same user-visible alarm as the localStorage rail so a
      // caller that ignores the promise still cannot show a false success.
      var settled = window.SMSOfflineDB.outboxEnqueue(row)
        .then(function () {
          updateBar();
          flushIfOnline();
          return { ok: true, storage: 'indexeddb', id: row.id };
        })
        .catch(function (err) {
          emitStorageAlert('error', writeFailedMessage(isQuotaError(err) ? 'quota_exceeded' : 'storage_unavailable'));
          return { ok: false, reason: 'indexeddb_write_failed', error: err };
        });
      return { ok: true, storage: 'indexeddb', id: row.id, settled: settled };
    }
    var rows = readOutboxLS();
    var lsRow = { id: row.id, payload: payload, ts: new Date().toISOString(), owner: owner };
    var cap = capacityForNewRow(rows, lsRow);
    if (!cap.ok) {
      // REFUSE-NEW: keep every older unsynced row, reject this one loudly.
      emitStorageAlert('error', outboxFullMessage(cap));
      updateBar();
      flushIfOnline();
      return { ok: false, reason: 'outbox_full', detail: cap.reason, queued: rows.length };
    }
    rows.push(lsRow);
    var written = writeOutboxLS(rows, cap.serialized);
    if (!written.ok) {
      emitStorageAlert('error', writeFailedMessage(written.reason));
      updateBar();
      return { ok: false, reason: written.reason, queued: rows.length - 1 };
    }
    if (cap.warn) {
      warnStorageOnce(
        'Offline storage is nearly full — ' +
          cap.rows +
          ' of ' +
          MAX_OUTBOX_ROWS +
          ' item(s) queued on this device. Reconnect and sync soon or new ' +
          'entries will be refused.'
      );
    }
    updateBar();
    flushIfOnline();
    return { ok: true, storage: 'localstorage', id: row.id, queued: cap.rows };
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
      var pruned = writeOutboxLS(remaining);
      if (!pruned.ok) {
        // The shrunken list did not persist, so the pre-flush list is still
        // on disk. Nothing is LOST (idempotency_key makes the replay safe),
        // but the queue will not drain — tell the user instead of looping
        // silently forever.
        emitStorageAlert(
          'error',
          'Sync problem — this device would not update its offline queue, ' +
            'so synced items may be sent again. Your work is not lost. ' +
            'Free up space on this device.'
        );
      }
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
  // Published so producer UIs and tests can reason about capacity without
  // duplicating the constants (see REFUSE-NEW policy at the top).
  window.rmcOfflineOutboxLimits = {
    maxRows: MAX_OUTBOX_ROWS,
    maxChars: MAX_OUTBOX_CHARS,
    backPressureRatio: BACK_PRESSURE_RATIO,
    storageKey: LS_KEY,
    alertElementId: STORAGE_ALERT_ID,
  };
  window.rmcOfflineDrainLocal = function () {
    var cleared = writeOutboxLS([]);
    if (!cleared.ok) {
      emitStorageAlert(
        'error',
        'This device would not clear its offline queue. Items may reappear ' +
          'until storage is available again.'
      );
    }
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
