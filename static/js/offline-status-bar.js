/**
 * Global connection status bar for offline-first portal.
 * Shows: Connected (green) | Offline – data will sync later (orange) | Syncing… (spinner).
 * Integrates with FormDraftSave and service worker sync.
 */
(function () {
  'use strict';

  var bar = null;
  var dot = null;
  var textEl = null;
  var spinnerEl = null;
  var syncingTimeout = null;
  var SYNCING_DURATION_MS = 4000;

  function getConfig() {
    return window.SMS_OFFLINE_CONFIG || {};
  }

  function setState(online, syncing) {
    if (!bar || !dot || !textEl || !spinnerEl) return;
    if (syncing) {
      bar.classList.remove('d-none');
      bar.classList.add('d-inline-flex');
      dot.style.background = '#ffc107';
      textEl.textContent = 'Syncing…';
      spinnerEl.classList.remove('d-none');
      return;
    }
    if (online) {
      bar.classList.remove('d-none');
      bar.classList.add('d-inline-flex');
      dot.style.background = '#198754';
      textEl.textContent = 'Connected';
      spinnerEl.classList.add('d-none');
    } else {
      bar.classList.remove('d-none');
      bar.classList.add('d-inline-flex');
      dot.style.background = '#fd7e14';
      textEl.textContent = 'Offline – data will sync later';
      spinnerEl.classList.add('d-none');
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

  function init() {
    var cfg = getConfig();
    if (!cfg.enabled) return;

    bar = document.getElementById('sms-offline-status-bar');
    dot = document.getElementById('sms-offline-status-dot');
    textEl = document.getElementById('sms-offline-status-text');
    spinnerEl = document.getElementById('sms-offline-status-spinner');
    if (!bar || !dot || !textEl) return;

    setState(navigator.onLine, false);

    window.addEventListener('online', function () {
      showSyncingTemporary();
    });
    window.addEventListener('offline', function () {
      setState(false, false);
    });

    document.addEventListener('sms-sync-start', showSyncingTemporary);
    document.addEventListener('sms-sync-end', function () {
      setState(navigator.onLine, false);
      if (syncingTimeout) {
        clearTimeout(syncingTimeout);
        syncingTimeout = null;
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.SMSOfflineStatusBar = { setState: setState, showSyncing: showSyncingTemporary };
})();
