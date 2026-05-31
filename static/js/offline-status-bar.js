/**
 * Global connection status bar for offline-first portal.
 * Shows: Connected (green) | Offline – N items will sync (orange) | Syncing… (spinner).
 * Optional: last synced at, resolve conflicts link, periodic retry when unreachable, queue length.
 */
(function () {
  'use strict';

  var bar = null;
  var dot = null;
  var textEl = null;
  var spinnerEl = null;
  var syncBtn = null;
  var lastSyncedEl = null;
  var conflictsBtn = null;
  var syncingTimeout = null;
  var queueLengthInterval = null;
  var reachabilityRetryCount = 0;
  var reachabilityRetryTimer = null;
  var pendingCount = 0;
  var notifyBadgeEl = null;
  var syncingWaitingLength = false;
  var syncingViaBatch = false;
  var serverUnreachable = false;
  var weAreSyncing = false;
  var syncingInOtherTab = false;
  var syncChannel = null;
  var exportQueueRequested = false;
  var SYNCING_DURATION_MS = 4000;
  var SYNC_CHANNEL_NAME = 'sms-offline-sync';
  var REACHABILITY_TIMEOUT_MS = 5000;
  var REACHABILITY_URL = '/health/';
  var REACHABILITY_RETRY_INTERVAL_MS = 30000;
  var REACHABILITY_MAX_RETRIES = 10;
  var QUEUE_LENGTH_POLL_MS = 8000;
  var LAST_SYNCED_KEY = 'sms-last-synced-at';
  var LAST_SYNCED_FAILED_KEY = 'sms-last-synced-failed-count';
  var CONFLICTS_KEY = 'sms-sync-conflicts';

  function getConfig() {
    return window.SMS_OFFLINE_CONFIG || {};
  }

  function getStoredConflicts() {
    try {
      var raw = localStorage.getItem(CONFLICTS_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (_) { return []; }
  }
  function setStoredConflicts(list) {
    try {
      if (!list || list.length === 0) localStorage.removeItem(CONFLICTS_KEY);
      else localStorage.setItem(CONFLICTS_KEY, JSON.stringify(list));
    } catch (_) {}
  }
  function getLastSyncedAt() {
    var v = localStorage.getItem(LAST_SYNCED_KEY);
    return v ? parseInt(v, 10) : 0;
  }
  function setLastSyncedAt(ms, failedCount) {
    try {
      localStorage.setItem(LAST_SYNCED_KEY, String(ms || 0));
      if (failedCount != null && failedCount !== 0) localStorage.setItem(LAST_SYNCED_FAILED_KEY, String(failedCount));
      else try { localStorage.removeItem(LAST_SYNCED_FAILED_KEY); } catch (_) {}
    } catch (_) {}
  }
  function formatLastSynced(ms) {
    if (!ms) return '';
    var sec = Math.floor((Date.now() - ms) / 1000);
    if (sec < 10) return 'Last synced just now';
    if (sec < 60) return 'Last synced ' + sec + 's ago';
    var min = Math.floor(sec / 60);
    if (min === 1) return 'Last synced 1 min ago';
    if (min < 60) return 'Last synced ' + min + ' min ago';
    var hr = Math.floor(min / 60);
    if (hr === 1) return 'Last synced 1 hr ago';
    return 'Last synced ' + hr + ' hr ago';
  }
  function requestQueueLength() {
    if (!navigator.serviceWorker || !navigator.serviceWorker.controller) return;
    navigator.serviceWorker.controller.postMessage({ type: 'GET_QUEUE_LENGTH' });
  }
  function stopReachabilityRetry() {
    reachabilityRetryCount = 0;
    if (reachabilityRetryTimer) { clearTimeout(reachabilityRetryTimer); reachabilityRetryTimer = null; }
  }
  function stopQueueLengthPolling() {
    if (queueLengthInterval != null) {
      clearTimeout(queueLengthInterval);
      clearInterval(queueLengthInterval);
      queueLengthInterval = null;
    }
    pendingCount = 0;
  }

  /**
   * Check if the server is actually reachable (not just navigator.onLine).
   * Uses a lightweight GET to REACHABILITY_URL with no-store and a timeout.
   * @returns {Promise<boolean>}
   */
  function checkReachability() {
    var url = (getConfig().reachabilityUrl || REACHABILITY_URL);
    var controller = new AbortController();
    var timeoutId = setTimeout(function () { controller.abort(); }, REACHABILITY_TIMEOUT_MS);
    return fetch(url, { method: 'GET', cache: 'no-store', credentials: 'same-origin', signal: controller.signal })
      .then(function (response) {
        clearTimeout(timeoutId);
        return response && response.ok;
      })
      .catch(function () {
        clearTimeout(timeoutId);
        return false;
      });
  }

  function setState(online, syncing) {
    if (!bar || !dot || !textEl) return;
    if (syncing) {
      serverUnreachable = false;
      bar.classList.remove('d-none');
      bar.classList.add('d-inline-flex');
      dot.style.background = 'var(--ds-warning)';
      textEl.textContent = 'Syncing…';
      if (spinnerEl) spinnerEl.classList.remove('d-none');
      if (syncBtn) { syncBtn.disabled = true; syncBtn.style.visibility = 'hidden'; }
      if (lastSyncedEl) lastSyncedEl.classList.add('d-none');
      if (conflictsBtn) conflictsBtn.classList.add('d-none');
      return;
    }
    if (syncBtn) { syncBtn.disabled = false; syncBtn.style.visibility = ''; }
    if (online && syncingInOtherTab) {
      bar.classList.remove('d-none');
      bar.classList.add('d-inline-flex');
      dot.style.background = 'var(--ds-warning)';
      textEl.textContent = 'Syncing in another tab';
      if (spinnerEl) spinnerEl.classList.add('d-none');
      if (syncBtn) { syncBtn.disabled = true; syncBtn.style.visibility = 'hidden'; }
      if (lastSyncedEl) lastSyncedEl.classList.add('d-none');
      if (conflictsBtn) conflictsBtn.classList.add('d-none');
      return;
    }
    if (online && serverUnreachable) {
      bar.classList.remove('d-none');
      bar.classList.add('d-inline-flex');
      dot.style.background = 'var(--ds-danger)';
      textEl.textContent = 'Server unreachable';
      if (spinnerEl) spinnerEl.classList.add('d-none');
      if (lastSyncedEl) lastSyncedEl.classList.add('d-none');
      if (conflictsBtn) conflictsBtn.classList.add('d-none');
      return;
    }
    if (online) {
      stopReachabilityRetry();
      stopQueueLengthPolling();
      bar.classList.remove('d-none');
      bar.classList.add('d-inline-flex');
      dot.style.background = 'var(--ds-success)';
      textEl.textContent = 'Connected';
      if (spinnerEl) spinnerEl.classList.add('d-none');
      refreshLastSynced();
      refreshConflictsButton();
      refreshNotificationQueueBadge();
    } else {
      bar.classList.remove('d-none');
      bar.classList.add('d-inline-flex');
      dot.style.background = 'var(--ds-danger)';
      textEl.textContent = pendingCount > 0
        ? 'Offline – ' + pendingCount + ' item(s) will sync'
        : 'Offline – data will sync later';
      if (spinnerEl) spinnerEl.classList.add('d-none');
      if (lastSyncedEl) lastSyncedEl.classList.add('d-none');
      if (conflictsBtn) conflictsBtn.classList.add('d-none');
      refreshNotificationQueueBadge();
    }
  }
  function refreshLastSynced() {
    if (!lastSyncedEl) return;
    var ms = getLastSyncedAt();
    if (!ms) { lastSyncedEl.classList.add('d-none'); return; }
    var failed = 0;
    try { var v = localStorage.getItem(LAST_SYNCED_FAILED_KEY); if (v) failed = parseInt(v, 10) || 0; } catch (_) {}
    lastSyncedEl.textContent = formatLastSynced(ms) + (failed > 0 ? ' (' + failed + ' failed)' : '');
    lastSyncedEl.title = failed > 0 ? 'Last sync had ' + failed + ' failed item(s)' : 'Last sync';
    lastSyncedEl.classList.remove('d-none');
  }
  function refreshNotificationQueueBadge() {
    if (!notifyBadgeEl) return;
    if (pendingCount > 0) {
      notifyBadgeEl.textContent = String(pendingCount);
      notifyBadgeEl.classList.remove('d-none');
      notifyBadgeEl.setAttribute(
        'aria-label',
        pendingCount + ' queued item(s) including notifications — delivers when connected',
      );
    } else {
      notifyBadgeEl.classList.add('d-none');
    }
  }

  function conflictsPortalUrl() {
    var cfg = getConfig();
    return (cfg.offlineConflictsUrl || cfg.offline_conflicts_url || '').trim();
  }

  function refreshConflictsButton() {
    if (!conflictsBtn) return;
    var list = getStoredConflicts();
    if (list.length === 0) { conflictsBtn.classList.add('d-none'); conflictsBtn.textContent = 'Resolve conflicts'; return; }
    conflictsBtn.textContent = 'Resolve conflicts (' + list.length + ')';
    conflictsBtn.classList.remove('d-none');
  }
  function showConflictsModal() {
    var list = getStoredConflicts();
    var listEl = document.getElementById('sms-offline-conflicts-list');
    var modal = document.getElementById('sms-offline-conflicts-modal');
    var portalLink = document.getElementById('sms-offline-conflicts-portal-link');
    if (!listEl || !modal) return;
    var portalUrl = conflictsPortalUrl();
    if (portalLink) {
      if (portalUrl) {
        portalLink.href = portalUrl;
        portalLink.classList.remove('d-none');
      } else {
        portalLink.classList.add('d-none');
      }
    }
    listEl.innerHTML = '';
    list.forEach(function (item) {
      var li = document.createElement('li');
      li.className = 'list-group-item d-flex justify-content-between align-items-start';
      var path = (item.url || '').trim();
      var label = path.replace(/^\/api\//, '').replace(/\/$/, '') || 'Item';
      var msg = item.message || ('HTTP ' + (item.status || ''));
      if (item.conflict || item.status === 409) {
        msg = (msg ? msg + ' — ' : '') + 'Conflict with server record.';
      }
      var link = document.createElement('a');
      link.href = path ? path : '#';
      link.className = 'text-break';
      link.textContent = label;
      var small = document.createElement('small');
      small.className = 'text-body-secondary d-block';
      small.textContent = msg;
      var wrap = document.createElement('div');
      wrap.className = 'ms-2 me-auto';
      wrap.appendChild(link);
      wrap.appendChild(small);
      li.appendChild(wrap);
      listEl.appendChild(li);
    });
    if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
      var m = new bootstrap.Modal(modal);
      m.show();
    }
  }
  function clearConflictsAndClose() {
    setStoredConflicts([]);
    refreshConflictsButton();
    var modal = document.getElementById('sms-offline-conflicts-modal');
    if (modal && typeof bootstrap !== 'undefined' && bootstrap.Modal) {
      var m = bootstrap.Modal.getInstance(modal);
      if (m) m.hide();
    }
  }

  function showSyncingTemporary() {
    setState(true, true);
    if (syncingTimeout) clearTimeout(syncingTimeout);
    syncingTimeout = setTimeout(function () {
      syncingTimeout = null;
      setState(navigator.onLine, false);
    }, SYNCING_DURATION_MS);
  }

  function setServerUnreachable(flag) {
    serverUnreachable = !!flag;
  }

  function showUnreachableBriefly() {
    serverUnreachable = true;
    setState(true, false);
    if (typeof document.dispatchEvent === 'function') {
      document.dispatchEvent(new CustomEvent('sms-sync-unreachable', { bubbles: true }));
      document.dispatchEvent(new CustomEvent('showToast', {
        detail: { message: 'Server unreachable. Sync when connection is restored.', type: 'warning', duration: 4000 }
      }));
    }
  }

  function triggerSyncNow() {
    if (!navigator.serviceWorker || !navigator.serviceWorker.controller) return;
    stopReachabilityRetry();
    weAreSyncing = true;
    if (typeof BroadcastChannel !== 'undefined') {
      try {
        syncChannel = syncChannel || new BroadcastChannel(SYNC_CHANNEL_NAME);
        syncChannel.postMessage({ type: 'sync-busy' });
      } catch (_) {}
    }
    checkReachability().then(function (reachable) {
      if (!reachable) {
        weAreSyncing = false;
        if (syncChannel) try { syncChannel.postMessage({ type: 'sync-idle' }); } catch (_) {}
        setState(true, false);
        showUnreachableBriefly();
        return;
      }
      setState(true, true);
      if (syncingTimeout) clearTimeout(syncingTimeout);
      syncingTimeout = null;
      var dripOn = window.SMSSyncManager && typeof window.SMSSyncManager.getDripModeSync === 'function' && window.SMSSyncManager.getDripModeSync();
      if (dripOn && typeof window.SMSSyncManager.requestSyncBatch === 'function') {
        window.SMSSyncManager.requestSyncBatch(10);
      } else {
        navigator.serviceWorker.controller.postMessage({ type: 'REPLAY_SYNC_NOW' });
      }
      syncingTimeout = setTimeout(function () {
        syncingTimeout = null;
        weAreSyncing = false;
        if (syncChannel) try { syncChannel.postMessage({ type: 'sync-idle' }); } catch (_) {}
        setState(navigator.onLine, false);
      }, SYNCING_DURATION_MS);
    });
  }
  function startReachabilityRetry() {
    stopReachabilityRetry();
    reachabilityRetryCount = 0;
    function tick() {
      reachabilityRetryCount++;
      if (reachabilityRetryCount > REACHABILITY_MAX_RETRIES) {
        stopReachabilityRetry();
        return;
      }
      checkReachability().then(function (reachable) {
        if (!reachable) {
          reachabilityRetryTimer = setTimeout(tick, REACHABILITY_RETRY_INTERVAL_MS);
          return;
        }
        stopReachabilityRetry();
        serverUnreachable = false;
        showSyncingTemporary();
        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
          navigator.serviceWorker.controller.postMessage({ type: 'REPLAY_SYNC_NOW' });
        }
      });
    }
    reachabilityRetryTimer = setTimeout(tick, REACHABILITY_RETRY_INTERVAL_MS);
  }
  function startQueueLengthPolling() {
    stopQueueLengthPolling();
    requestQueueLength();
    queueLengthInterval = setTimeout(function () {
      queueLengthInterval = setInterval(function () { requestQueueLength(); }, QUEUE_LENGTH_POLL_MS);
    }, 500);
  }

  function init() {
    var cfg = getConfig();
    if (!cfg.enabled) return;

    bar = document.getElementById('sms-offline-status-bar');
    dot = document.getElementById('sms-offline-status-dot');
    textEl = document.getElementById('sms-offline-status-text');
    spinnerEl = document.getElementById('sms-offline-status-spinner');
    notifyBadgeEl = document.getElementById('sms-offline-notification-queue-badge');
    syncBtn = document.getElementById('sms-offline-sync-now-btn');
    lastSyncedEl = document.getElementById('sms-offline-status-last-synced');
    conflictsBtn = document.getElementById('sms-offline-conflicts-btn');
    if (!bar || !dot || !textEl) return;

    setState(navigator.onLine, false);
    if (!navigator.onLine) startQueueLengthPolling();

    if (syncBtn) syncBtn.addEventListener('click', function () { triggerSyncNow(); });
    if (conflictsBtn) conflictsBtn.addEventListener('click', function () { showConflictsModal(); });
    document.addEventListener('rmc-offline-conflicts-updated', function (ev) {
      var detail = ev && ev.detail ? ev.detail : {};
      var count = parseInt(detail.count, 10) || 0;
      if (count <= 0) return;
      var bar = document.getElementById('rmc-offline-sync-bar');
      if (bar) bar.setAttribute('data-server-conflicts', String(count));
      if (typeof document.dispatchEvent === 'function') {
        document.dispatchEvent(new CustomEvent('showToast', {
          detail: {
            message: count + ' queued item(s) need conflict resolution in Offline Sync.',
            type: 'warning',
            duration: 6000
          }
        }));
      }
    });
    var dismissBtn = document.getElementById('sms-offline-conflicts-dismiss-btn');
    if (dismissBtn) dismissBtn.addEventListener('click', clearConflictsAndClose);

    if (typeof BroadcastChannel !== 'undefined') {
      try {
        syncChannel = new BroadcastChannel(SYNC_CHANNEL_NAME);
        syncChannel.onmessage = function (e) {
          var msg = e && e.data;
          if (!msg || msg.type === undefined) return;
          if (msg.type === 'sync-busy' && !weAreSyncing) {
            syncingInOtherTab = true;
            setState(navigator.onLine, false);
          } else if (msg.type === 'sync-idle') {
            syncingInOtherTab = false;
            setState(navigator.onLine, false);
          }
        };
      } catch (_) {}
    }

    var showOfflineDebug = (typeof URLSearchParams !== 'undefined' && new URLSearchParams(window.location.search).get('offline_debug') === '1');
    if (showOfflineDebug && bar && navigator.serviceWorker && navigator.serviceWorker.controller) {
      var exportBtn = document.createElement('button');
      exportBtn.type = 'button';
      exportBtn.className = 'btn btn-link btn-sm p-0 ms-1 text-white-50 text-decoration-underline';
      exportBtn.style.fontSize = 'inherit';
      exportBtn.textContent = 'Export queue';
      exportBtn.setAttribute('aria-label', 'Copy queue to clipboard (debug)');
      exportBtn.addEventListener('click', function () {
        exportQueueRequested = true;
        navigator.serviceWorker.controller.postMessage({ type: 'GET_QUEUE_ITEMS', limit: 500 });
      });
      bar.appendChild(exportBtn);
    }

    if (navigator.serviceWorker) {
      navigator.serviceWorker.addEventListener('message', function (event) {
        var d = event.data;
        if (!d) return;
        if (d.type === 'sync-complete') {
          if (syncingTimeout) { clearTimeout(syncingTimeout); syncingTimeout = null; }
          weAreSyncing = false;
          syncingInOtherTab = false;
          if (syncChannel) try { syncChannel.postMessage({ type: 'sync-idle' }); } catch (_) {}
          pendingCount = 0;
          setState(navigator.onLine, false);
          var failed = d.failedCount || 0;
          setLastSyncedAt(Date.now(), failed);
          refreshLastSynced();
          var items = d.failedItems || [];
          if (items.length > 0) {
            var existing = getStoredConflicts();
            var combined = existing.concat(items);
            setStoredConflicts(combined);
            refreshConflictsButton();
          }
          var hasHttpConflict = items.some(function (it) {
            return it && (it.conflict || it.status === 409);
          });
          var portalUrl = conflictsPortalUrl();
          if (hasHttpConflict && portalUrl && typeof document.dispatchEvent === 'function') {
            document.dispatchEvent(new CustomEvent('showToast', {
              detail: {
                message: 'Server conflict detected. Open the Offline Sync conflicts screen to choose keep mine / use latest.',
                type: 'warning',
                duration: 7000
              }
            }));
          }
          if (failed > 0 && typeof document.dispatchEvent === 'function') {
            document.dispatchEvent(new CustomEvent('showToast', {
              detail: { message: failed + ' item(s) could not sync (e.g. conflict or invalid). Use Resolve conflicts to see details.', type: 'warning', duration: 5000 }
            }));
          }
        }
        if (d.type === 'queue-length') {
          pendingCount = d.total != null ? d.total : 0;
          refreshNotificationQueueBadge();
          var maxQ = parseInt((getConfig().maxQueueItems || 500), 10);
          if (pendingCount >= maxQ * 0.9) {
            document.dispatchEvent(new CustomEvent('rmc:warning', {
              detail: { message: 'Offline queue nearly full — sync when connected.', duration: 6000 }
            }));
          }
          if (pendingCount >= 0 && typeof fetch === 'function') {
            var metricsUrl = (getConfig().offlineQueueMetricsUrl || '').trim();
            if (!metricsUrl && window.RMCPlatformSurface && window.RMCPlatformSurface.url) {
              metricsUrl = window.RMCPlatformSurface.url('offline_queue_metrics');
            }
            if (!metricsUrl) return;
            if (!metricsUrl.startsWith('http')) metricsUrl = window.location.origin + (metricsUrl.startsWith('/') ? metricsUrl : '/' + metricsUrl);
            fetch(metricsUrl, {
              method: 'POST',
              credentials: 'same-origin',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || '' },
              body: JSON.stringify({ total: pendingCount, by_type: d.by_type || { attendance: d.attendance || 0, grade: d.grade || 0, api: d.api || 0 } })
            }).catch(function () {});
          }
          if (syncingWaitingLength) {
            syncingWaitingLength = false;
            var dripOn = window.SMSSyncManager && typeof window.SMSSyncManager.getDripModeSync === 'function' && window.SMSSyncManager.getDripModeSync();
            if (dripOn) {
              setState(navigator.onLine, false);
            } else {
              var threshold = (getConfig().batchReplayThreshold != null ? getConfig().batchReplayThreshold : 5);
              if (pendingCount >= threshold && pendingCount > 0 && navigator.serviceWorker.controller) {
                syncingViaBatch = true;
                navigator.serviceWorker.controller.postMessage({ type: 'GET_QUEUE_ITEMS', limit: pendingCount + 50 });
              } else {
                if (navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage({ type: 'REPLAY_SYNC_NOW' });
                syncingTimeout = setTimeout(function () { syncingTimeout = null; setState(navigator.onLine, false); }, SYNCING_DURATION_MS);
              }
            }
          }
          if (!navigator.onLine && textEl) {
            textEl.textContent = pendingCount > 0
              ? 'Offline – ' + pendingCount + ' item(s) will sync'
              : 'Offline – data will sync later';
          }
        }
        if (d.type === 'queue-items' && d.items && Array.isArray(d.items)) {
          if (exportQueueRequested) {
            exportQueueRequested = false;
            try {
              var json = JSON.stringify(d.items, null, 2);
              if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(json).then(function () {
                  if (typeof document.dispatchEvent === 'function') {
                    document.dispatchEvent(new CustomEvent('showToast', { detail: { message: 'Queue copied to clipboard (' + d.items.length + ' items)', type: 'info', duration: 3000 } }));
                  }
                }).catch(function () {
                  if (typeof document.dispatchEvent === 'function') {
                    document.dispatchEvent(new CustomEvent('showToast', { detail: { message: 'Copy failed. Queue: ' + d.items.length + ' items.', type: 'warning', duration: 3000 } }));
                  }
                });
              } else {
                if (typeof document.dispatchEvent === 'function') {
                  document.dispatchEvent(new CustomEvent('showToast', { detail: { message: 'Queue: ' + d.items.length + ' items (clipboard not available)', type: 'info', duration: 3000 } }));
                }
              }
            } catch (_) {}
            return;
          }
          if (!syncingViaBatch) return;
          syncingViaBatch = false;
          var ids = d.items.map(function (it) { return it.id; }).filter(Boolean);
          var body = JSON.stringify({ items: d.items });
          var replayUrl = (getConfig().offlineReplayBatchUrl || '').trim();
          if (!replayUrl && window.RMCPlatformSurface && window.RMCPlatformSurface.url) {
            replayUrl = window.RMCPlatformSurface.url('offline_replay_batch');
          }
          if (!replayUrl) return;
          fetch(replayUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || '' }, body: body, credentials: 'same-origin' })
            .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
            .then(function (r) {
              if (r.ok && r.data && r.data.removed_ids && r.data.removed_ids.length > 0 && navigator.serviceWorker.controller) {
                navigator.serviceWorker.controller.postMessage({ type: 'REMOVE_QUEUE_ITEMS', ids: r.data.removed_ids });
              }
              var failed = (r.data && r.data.failed_count) != null ? r.data.failed_count : (r.ok ? 0 : ids.length);
              var failedItems = (r.data && r.data.failed_items) ? r.data.failed_items : [];
              pendingCount = 0;
              setState(navigator.onLine, false);
              setLastSyncedAt(Date.now(), failed);
              refreshLastSynced();
              if (failedItems.length > 0) {
                var existing = getStoredConflicts();
                var combined = existing.concat(failedItems);
                setStoredConflicts(combined);
                refreshConflictsButton();
              }
              if (failed > 0 && typeof document.dispatchEvent === 'function') {
                document.dispatchEvent(new CustomEvent('showToast', { detail: { message: failed + ' item(s) could not sync.', type: 'warning', duration: 5000 } }));
              }
            })
            .catch(function () {
              syncingViaBatch = false;
              setState(navigator.onLine, false);
              if (navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage({ type: 'REPLAY_SYNC_NOW' });
              syncingTimeout = setTimeout(function () { syncingTimeout = null; setState(navigator.onLine, false); }, SYNCING_DURATION_MS);
            });
        }
      });
    }

    window.addEventListener('online', function () {
      stopQueueLengthPolling();
      pendingCount = 0;
      checkReachability().then(function (reachable) {
        if (!reachable) {
          setState(true, false);
          showUnreachableBriefly();
          startReachabilityRetry();
          return;
        }
        var doReplay = function () {
          showSyncingTemporary();
          if (navigator.serviceWorker && navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({ type: 'REPLAY_SYNC_NOW' });
          }
        };
        if (window.SMSSyncManager && typeof window.SMSSyncManager.getDripMode === 'function') {
          window.SMSSyncManager.getDripMode().then(function (drip) {
            if (drip) {
              setState(true, false);
              return;
            }
            doReplay();
          }).catch(function () { doReplay(); });
        } else {
          doReplay();
        }
      });
    });
    window.addEventListener('offline', function () {
      stopReachabilityRetry();
      serverUnreachable = false;
      setState(false, false);
      startQueueLengthPolling();
    });

    setInterval(refreshLastSynced, 60000);

    document.addEventListener('sms-sync-start', showSyncingTemporary);
    document.addEventListener('sms-sync-end', function () {
      setState(navigator.onLine, false);
      if (syncingTimeout) { clearTimeout(syncingTimeout); syncingTimeout = null; }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.SMSOfflineStatusBar = { setState: setState, showSyncing: showSyncingTemporary, triggerSyncNow: triggerSyncNow, checkReachability: checkReachability, setServerUnreachable: setServerUnreachable };
})();
