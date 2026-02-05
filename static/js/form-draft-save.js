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
  var DEFAULT_MAX_AGE_HOURS = 24;
  var DEBOUNCE_MS = 1500;

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
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function setDraft(key, data) {
    try {
      localStorage.setItem(storageKey(key), JSON.stringify(data));
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
    form.addEventListener('submit', function () {
      removeDraft(key);
    });

    window.addEventListener('beforeunload', function () {
      save();
    });

    var existing = getDraft(key);
    if (existing && !isExpired(existing, maxAgeHours) && Object.keys(existing.fields).length > 0) {
      showResumeBanner(form, key, existing, maxAgeHours);
    }
  };

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
    removeDraft: removeDraft
  };
})();
