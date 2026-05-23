/**
 * Form draft save for long forms (e.g. mark entry, attendance).
 * Mitigates power loss / browser close: saves form state to localStorage and
 * offers "Resume draft?" on next load. Use on teacher mark entry and other
 * critical long forms in low-connectivity environments (Buea/Cameroon).
 *
 * Usage:
 *   Form must have: data-draft-key="unique_key" (e.g. marks_123)
 *   Optional: data-draft-max-age-hours="24" (default 24)
 *   Then call: FormDraftSave.init(document.querySelector('form[data-draft-key]'));
 */
(function () {
  'use strict';

  var STORAGE_PREFIX = 'sms_draft_';
  var PENDING_SUBMISSIONS_KEY = 'sms_pending_mark_submissions';
  var DEFAULT_MAX_AGE_HOURS = 24;
  var DEBOUNCE_MS = 1500;
  var PENDING_MAX_AGE_MS = 48 * 60 * 60 * 1000; // 48h
  var PENDING_MAX_COUNT = 30; // cap queue to avoid localStorage bloat
  var DRAFT_ENCRYPTION_KEY_STORAGE = 'sms-draft-encryption-key';

  function getDraftEncryptionKey() {
    try {
      var cfg = window.SMS_OFFLINE_CONFIG || {};
      if (cfg.draftEncryptionKey) return cfg.draftEncryptionKey;
      return sessionStorage.getItem(DRAFT_ENCRYPTION_KEY_STORAGE) || '';
    } catch (e) { return ''; }
  }

  function maybeEncryptDraft(str) {
    var key = getDraftEncryptionKey();
    if (!key || typeof str !== 'string') return str;
    try { return btoa(encodeURIComponent(str)); } catch (e) { return str; }
  }
  function maybeDecryptDraft(str) {
    var key = getDraftEncryptionKey();
    if (!key || typeof str !== 'string') return str;
    try { return decodeURIComponent(atob(str)); } catch (e) { return str; }
  }

  function getOfflineConfig() {
    var cfg = window.SMS_OFFLINE_CONFIG || {};
    return {
      enabled: cfg.enabled !== false,
      formQueueEnabled: cfg.formQueueEnabled !== false,
      gradeSyncEnabled: cfg.gradeSyncEnabled !== false,
      offlineEnqueueUrl: cfg.offlineEnqueueUrl || cfg.offline_enqueue_url || ''
    };
  }

  function buildGenericPayload(form) {
    var payload = {};
    var inputs = form.querySelectorAll('input, select, textarea');
    for (var i = 0; i < inputs.length; i++) {
      var el = inputs[i];
      var name = el.name;
      if (!name || name === 'csrfmiddlewaretoken') continue;
      if (el.type === 'checkbox') {
        if (el.checked) payload[name] = el.value || true;
      } else if (el.type === 'radio') {
        if (el.checked) payload[name] = el.value;
      } else if (el.value !== '') {
        payload[name] = el.value;
      }
    }
    return payload;
  }

  function enqueueTypedAction(form, actionType, draftKey) {
    var payload = buildGenericPayload(form);
    var idem = (form.getAttribute('data-rmc-offline-idempotency') || '').trim();
    if (!idem) {
      idem = actionType.replace(/[^a-zA-Z0-9._-]/g, '-') + '-' + (draftKey || Date.now());
    }
    var body = {
      action_type: actionType,
      payload: payload,
      idempotency_key: idem.slice(0, 128)
    };
    if (typeof window.rmcOfflineEnqueue === 'function') {
      window.rmcOfflineEnqueue(body);
      return true;
    }
    var pending = getPendingSubmissions();
    if (pending.length >= PENDING_MAX_COUNT) return false;
    pending.push({
      typed: true,
      action_type: body.action_type,
      payload: body.payload,
      idempotency_key: body.idempotency_key,
      savedAt: Date.now()
    });
    setPendingSubmissions(pending);
    return true;
  }

  function postTypedEnqueue(enqueueUrl, csrf, item) {
    return fetch(enqueueUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        action_type: item.action_type,
        payload: item.payload || {},
        idempotency_key: item.idempotency_key || ''
      })
    }).then(function (res) {
      return res.ok;
    }).catch(function () {
      return false;
    });
  }

  function storageKey(key) {
    return STORAGE_PREFIX + (key || '').replace(/[^a-zA-Z0-9_-]/g, '_');
  }

  function serializeForm(form) {
    var data = { savedAt: Date.now(), fields: {} };
    var inputs = form.querySelectorAll('input, select, textarea');
    for (var i = 0; i < inputs.length; i++) {
      var el = inputs[i];
      var name = el.name;
      if (!name || el.type === 'hidden' && name === 'csrfmiddlewaretoken') continue;
      if (el.type === 'checkbox' || el.type === 'radio') {
        if (el.checked) data.fields[name] = el.value || 'on';
      } else {
        data.fields[name] = el.value;
      }
    }
    return data;
  }

  function restoreForm(form, data) {
    if (!data || !data.fields) return;
    var fields = data.fields;
    for (var name in fields) {
      var el = form.querySelector('[name="' + name.replace(/"/g, '\\"') + '"]');
      if (el) {
        if (el.type === 'checkbox' || el.type === 'radio') {
          el.checked = (el.value === fields[name] || (el.value || 'on') === fields[name]);
        } else {
          el.value = fields[name] || '';
        }
      }
    }
  }

  function getDraft(key) {
    try {
      var raw = localStorage.getItem(storageKey(key));
      if (!raw) return null;
      raw = maybeDecryptDraft(raw);
      if (raw === null) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function setDraft(key, data) {
    try {
      var str = JSON.stringify(data);
      str = maybeEncryptDraft(str);
      localStorage.setItem(storageKey(key), str);
      return true;
    } catch (e) {
      return false;
    }
  }

  function removeDraft(key) {
    try {
      localStorage.removeItem(storageKey(key));
    } catch (e) {}
  }

  function getCsrf() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  function getPendingSubmissions() {
    try {
      var raw = localStorage.getItem(PENDING_SUBMISSIONS_KEY);
      if (raw) raw = maybeDecryptDraft(raw);
      var list = raw ? JSON.parse(raw) : [];
      var now = Date.now();
      return list.filter(function (p) { return p.savedAt && (now - p.savedAt) < PENDING_MAX_AGE_MS; });
    } catch (e) {
      return [];
    }
  }

  function setPendingSubmissions(list) {
    try {
      var str = JSON.stringify(list);
      str = maybeEncryptDraft(str);
      localStorage.setItem(PENDING_SUBMISSIONS_KEY, str);
    } catch (e) {}
  }

  function isExpired(data, maxAgeHours) {
    if (!data || !data.savedAt) return true;
    var ageHours = (Date.now() - data.savedAt) / (1000 * 60 * 60);
    return ageHours > maxAgeHours;
  }

  function debounce(fn, ms) {
    var t;
    return function () {
      clearTimeout(t);
      t = setTimeout(fn, ms);
    };
  }

  function FormDraftSave() {
    this._saveHandlers = [];
  }

  FormDraftSave.prototype.init = function (form) {
    if (!form || !form.getAttribute('data-draft-key')) return;
    var key = form.getAttribute('data-draft-key');
    var maxAgeHours = parseInt(form.getAttribute('data-draft-max-age-hours') || '', 10) || DEFAULT_MAX_AGE_HOURS;

    var self = this;
    var save = function () {
      var data = serializeForm(form);
      if (Object.keys(data.fields).length) setDraft(key, data);
    };

    var debouncedSave = debounce(save, DEBOUNCE_MS);

    form.addEventListener('input', debouncedSave);
    form.addEventListener('change', debouncedSave);
    form.addEventListener('submit', function (e) {
      var offlineCfg = getOfflineConfig();
      if (!navigator.onLine && form.getAttribute('data-draft-key') && offlineCfg.enabled && offlineCfg.formQueueEnabled) {
        var explicitAction = (form.getAttribute('data-rmc-offline-action') || '').trim();
        if (explicitAction) {
          e.preventDefault();
          var atCap = !enqueueTypedAction(form, explicitAction, key);
          removeDraft(key);
          showOfflineSavedForSyncBanner(form, atCap);
          return;
        }
        if (form.getAttribute('data-rmc-offline-form')) {
          e.preventDefault();
          removeDraft(key);
          return;
        }
        e.preventDefault();
        var pending = getPendingSubmissions();
        if (pending.length >= PENDING_MAX_COUNT) {
          showOfflineSavedForSyncBanner(form, true);
          return;
        }
        var url = (form.getAttribute('action') || window.location.href).split('?')[0];
        var fd = new FormData(form);
        var body = Array.from(fd.entries()).map(function (pair) {
          return encodeURIComponent(pair[0]) + '=' + encodeURIComponent(pair[1] || '');
        }).join('&');
        pending.push({ url: url, body: body, savedAt: Date.now() });
        setPendingSubmissions(pending);
        removeDraft(key);
        showOfflineSavedForSyncBanner(form, false);
        return;
      }
      removeDraft(key);
      hideOfflineBanner();
      hideSyncBanner();
    });

    window.addEventListener('beforeunload', function () {
      save();
    });

    var existing = getDraft(key);
    if (existing && !isExpired(existing, maxAgeHours) && Object.keys(existing.fields).length > 0) {
      showResumeBanner(form, key, existing, maxAgeHours);
    }

    offlineSyncBanner(form, key);
    if (getOfflineConfig().enabled && form.getAttribute('data-draft-key')) {
      if (!form.querySelector('.sms-offline-works-badge')) {
        var badge = document.createElement('span');
        badge.className = 'sms-offline-works-badge badge bg-secondary bg-opacity-75 text-white small align-middle';
        badge.setAttribute('aria-label', 'This form works offline');
        badge.title = 'This form works offline. Your changes are saved locally and will sync when you\'re back online.';
        badge.textContent = 'Works offline';
        badge.style.cssText = 'font-weight: 500; letter-spacing: 0.02em;';
        form.insertBefore(badge, form.firstChild);
      }
      var hintEl = form.querySelector('.sms-offline-form-hint');
      if (!hintEl) {
        var hintText = form.getAttribute('data-offline-hint') || 'Your changes are saved locally and will sync when you\'re back online.';
        hintEl = document.createElement('p');
        hintEl.className = 'sms-offline-form-hint text-muted small mt-2 mb-0';
        hintEl.setAttribute('aria-live', 'polite');
        hintEl.textContent = hintText;
        form.appendChild(hintEl);
      }
    }
  };

  function hideOfflineBanner() {
    var el = document.getElementById('sms-offline-draft-banner');
    if (el) el.remove();
  }

  function hideSyncBanner() {
    var el = document.getElementById('sms-sync-draft-banner');
    if (el) el.remove();
  }

  function hideUnsyncedBanner() {
    var el = document.getElementById('sms-unsynced-submissions-banner');
    if (el) el.remove();
  }

  function showOfflineSavedForSyncBanner(form, atCap) {
    var pending = getPendingSubmissions();
    var n = pending.length;
    if (document.getElementById('sms-offline-saved-for-sync-banner')) return;
    var banner = document.createElement('div');
    banner.id = 'sms-offline-saved-for-sync-banner';
    banner.className = 'alert alert-dismissible fade show mb-3';
    banner.classList.add(atCap ? 'alert-warning' : 'alert-info');
    banner.setAttribute('role', 'alert');
    var msg = atCap
      ? '<strong>Queue full.</strong> Sync ' + n + ' pending submission(s) when back online before saving more.'
      : '<strong>Saved for sync.</strong> You are offline. ' + n + ' submission(s) will be sent when you are back online.';
    banner.innerHTML = msg + ' <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
    form.parentNode.insertBefore(banner, form);
  }

  function syncPendingSubmissions(done) {
    var pending = getPendingSubmissions();
    if (pending.length === 0) {
      if (done) done(false);
      return;
    }
    try {
      document.dispatchEvent(new CustomEvent('sms-sync-start', { bubbles: true }));
    } catch (e) {}
    var csrf = getCsrf();
    var offlineCfg = getOfflineConfig();
    var enqueueUrl = offlineCfg.offlineEnqueueUrl;
    var i = 0;
    var stillPending = [];
    function next() {
      if (i >= pending.length) {
        setPendingSubmissions(stillPending);
        hideUnsyncedBanner();
        try {
          document.dispatchEvent(new CustomEvent('sms-sync-end', { bubbles: true }));
        } catch (e) {}
        if (done) done(stillPending.length > 0);
        return;
      }
      var p = pending[i];
      var current = i;
      if (p.typed && p.action_type && enqueueUrl) {
        postTypedEnqueue(enqueueUrl, csrf, p).then(function (ok) {
          if (!ok) stillPending.push(p);
          i = current + 1;
          next();
        });
        return;
      }
      fetch(p.url, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' },
        body: p.body,
        credentials: 'same-origin'
      }).then(function (res) {
        if (!res.ok) stillPending.push(p);
        i = current + 1;
        next();
      }).catch(function () {
        stillPending.push(p);
        i = current + 1;
        next();
      });
    }
    next();
  }

  function showUnsyncedBannerIfAny(container, label) {
    var pending = getPendingSubmissions();
    if (pending.length === 0 || document.getElementById('sms-unsynced-submissions-banner')) return;
    var text = label || 'Unsynced submissions';
    var parent = container && container.parentNode ? container.parentNode : document.body;
    var banner = document.createElement('div');
    banner.id = 'sms-unsynced-submissions-banner';
    banner.className = 'alert alert-warning alert-dismissible fade show mb-3';
    banner.setAttribute('role', 'alert');
    banner.innerHTML =
      '<strong>' + text + ':</strong> ' + pending.length + ' saved while offline. ' +
      '<button type="button" class="btn btn-sm btn-warning ms-2 btn-sync-pending-now" aria-label="Sync unsynced submissions to server">Sync now</button> ' +
      '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
    parent.insertBefore(banner, container);
    var syncBtn = banner.querySelector('.btn-sync-pending-now');
    var msgStrong = banner.querySelector('strong');
    syncBtn.addEventListener('click', function runSync() {
      syncBtn.disabled = true;
      syncBtn.textContent = 'Syncing…';
      syncBtn.setAttribute('aria-busy', 'true');
      syncPendingSubmissions(function (hadFailures) {
        syncBtn.removeAttribute('aria-busy');
        if (hadFailures) {
          syncBtn.disabled = false;
          syncBtn.textContent = 'Sync now';
          banner.classList.remove('alert-warning');
          banner.classList.add('alert-danger');
          if (msgStrong) msgStrong.textContent = 'Some submissions could not be synced.';
          var textAfter = banner.childNodes;
          for (var t = 0; t < textAfter.length; t++) {
            if (textAfter[t].nodeType === 3) {
              textAfter[t].textContent = ' Try again or check your connection. ';
              break;
            }
          }
        } else {
          window.location.reload();
        }
      });
    });
  }

  function offlineSyncBanner(form, key) {
    function showOffline() {
      if (document.getElementById('sms-offline-draft-banner')) return;
      var banner = document.createElement('div');
      banner.id = 'sms-offline-draft-banner';
      banner.className = 'alert alert-secondary alert-dismissible fade show mb-3';
      banner.setAttribute('role', 'alert');
      banner.innerHTML = '<strong>Offline.</strong> Changes are saved in your browser. They will sync when you are back online. <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
      form.parentNode.insertBefore(banner, form);
    }

    function showSyncPrompt() {
      if (!getDraft(key) || document.getElementById('sms-sync-draft-banner')) return;
      var banner = document.createElement('div');
      banner.id = 'sms-sync-draft-banner';
      banner.className = 'alert alert-success alert-dismissible fade show mb-3';
      banner.setAttribute('role', 'alert');
      banner.innerHTML =
        '<strong>Back online.</strong> Submit your draft to save marks to the server. ' +
        '<button type="button" class="btn btn-sm btn-success ms-2 btn-sync-draft-now">Submit draft now</button> ' +
        '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
      form.parentNode.insertBefore(banner, form);
      banner.querySelector('.btn-sync-draft-now').addEventListener('click', function () {
        var data = getDraft(key);
        if (data && data.fields) restoreForm(form, data);
        form.requestSubmit();
        banner.remove();
      });
    }

    if (!navigator.onLine) showOffline();
    window.addEventListener('offline', showOffline);
    window.addEventListener('online', function () {
      hideOfflineBanner();
      showSyncPrompt();
      var offlineCfg = getOfflineConfig();
      if (offlineCfg.enabled && offlineCfg.formQueueEnabled) {
        showUnsyncedBannerIfAny(form, form.getAttribute('data-draft-pending-label') || null);
      }
    });

    var offlineCfg = getOfflineConfig();
    if (offlineCfg.enabled && offlineCfg.formQueueEnabled) {
      showUnsyncedBannerIfAny(form, form.getAttribute('data-draft-pending-label') || null);
    }
  }

  function showResumeBanner(form, key, data, maxAgeHours) {
    var banner = document.createElement('div');
    banner.className = 'alert alert-warning alert-dismissible fade show mb-3';
    banner.setAttribute('role', 'alert');
    banner.innerHTML =
      '<strong>Resume draft?</strong> A previous draft was saved (e.g. after a power cut or closed tab). ' +
      '<button type="button" class="btn btn-sm btn-outline-warning me-2 btn-restore-draft" data-draft-key="' + key.replace(/"/g, '&quot;') + '">Restore draft</button> ' +
      '<button type="button" class="btn btn-sm btn-outline-secondary btn-discard-draft" data-draft-key="' + key.replace(/"/g, '&quot;') + '">Discard</button> ' +
      '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';

    form.parentNode.insertBefore(banner, form);

    banner.querySelector('.btn-restore-draft').addEventListener('click', function () {
      restoreForm(form, data);
      removeDraft(key);
      banner.remove();
    });

    banner.querySelector('.btn-discard-draft').addEventListener('click', function () {
      removeDraft(key);
      banner.remove();
    });
  }

  window.FormDraftSave = {
    init: function (form) {
      var s = new FormDraftSave();
      s.init(form);
    },
    getDraft: getDraft,
    setDraft: setDraft,
    removeDraft: removeDraft,
    getPendingSubmissions: getPendingSubmissions,
    syncPendingSubmissions: syncPendingSubmissions,
    showUnsyncedBannerIfAny: showUnsyncedBannerIfAny
  };

  // CSP-clean auto-init: any form that opts in via data-draft-key picks up
  // draft-save automatically, so per-page <script> shims are not required.
  // Templates that previously did `FormDraftSave.init(document.getElementById(...))`
  // can just declare `data-draft-key="..."` on the <form> and this hook does the rest.
  function _autoInitFormDraftSave() {
    var forms = document.querySelectorAll('form[data-draft-key]');
    for (var i = 0; i < forms.length; i++) {
      window.FormDraftSave.init(forms[i]);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _autoInitFormDraftSave);
  } else {
    _autoInitFormDraftSave();
  }
})();
