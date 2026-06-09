/* Encrypted IndexedDB draft support for Setup Studio intake wizards. */
(function (global) {
  "use strict";

  var SAVE_DELAY_MS = 500;
  var MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

  function draftKey(form) {
    return [
      "wizard",
      form.getAttribute("data-rmc-wizard-school-id") || "preview",
      form.getAttribute("data-rmc-wizard-key") || "",
      form.getAttribute("data-rmc-wizard-step-key") || "",
    ].join(":");
  }

  function serialize(form) {
    var fields = {};
    form.querySelectorAll("input, select, textarea").forEach(function (field) {
      if (!field.name || field.name === "csrfmiddlewaretoken") return;
      if (field.type === "file" || field.type === "password") return;
      if ((field.type === "checkbox" || field.type === "radio") && !field.checked) return;
      var values = field.tagName === "SELECT" && field.multiple
        ? Array.prototype.map.call(field.selectedOptions, function (option) {
          return option.value;
        })
        : [field.value];
      if (!Object.prototype.hasOwnProperty.call(fields, field.name)) {
        fields[field.name] = values.length === 1 ? values[0] : values;
        return;
      }
      var existing = Array.isArray(fields[field.name])
        ? fields[field.name]
        : [fields[field.name]];
      fields[field.name] = existing.concat(values);
    });
    return { fields: fields, saved_at: Date.now() };
  }

  function restore(form, payload) {
    Object.keys((payload && payload.fields) || {}).forEach(function (name) {
      var escaped = global.CSS && global.CSS.escape
        ? global.CSS.escape(name)
        : name.replace(/["\\]/g, "\\$&");
      var fields = form.querySelectorAll('[name="' + escaped + '"]');
      var savedValues = Array.isArray(payload.fields[name])
        ? payload.fields[name].map(String)
        : [String(payload.fields[name])];
      fields.forEach(function (field) {
        if (field.type === "checkbox" || field.type === "radio") {
          field.checked = savedValues.indexOf(String(field.value)) !== -1;
        } else if (field.tagName === "SELECT" && field.multiple) {
          Array.prototype.forEach.call(field.options, function (option) {
            option.selected = savedValues.indexOf(String(option.value)) !== -1;
          });
        } else {
          field.value = savedValues[0];
        }
        field.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
  }

  function bind(form) {
    if (!form || form.getAttribute("data-rmc-offline-intake") !== "1") return;
    if (!global.SMSOfflineDB || !global.RmcOfflineCrypto) return;
    var crypto = global.RmcOfflineCrypto.createOfflineCryptoWrapper();
    if (!crypto.supported) return;
    var key = draftKey(form);
    var timer = null;
    var banner = document.querySelector("[data-rmc-wizard-restore-banner]");
    var restoreButton = banner && banner.querySelector('[data-rmc-wizard-restore-action="restore"]');
    var discardButton = banner && banner.querySelector('[data-rmc-wizard-restore-action="discard"]');
    var pendingPayload = null;

    function removeDraft() {
      return global.SMSOfflineDB.deleteWizardDraft(key).then(function () {
        if (banner) banner.hidden = true;
      });
    }

    function saveDraft() {
      var payload = serialize(form);
      if (!Object.keys(payload.fields).length) return Promise.resolve();
      return crypto.encrypt(payload).then(function (encrypted) {
        return global.SMSOfflineDB.putWizardDraft({
          key: key,
          school_id: form.getAttribute("data-rmc-wizard-school-id") || "",
          wizard_key: form.getAttribute("data-rmc-wizard-key") || "",
          step_key: form.getAttribute("data-rmc-wizard-step-key") || "",
          updated_at: payload.saved_at,
          encrypted: encrypted,
        });
      });
    }

    function queueSave() {
      global.clearTimeout(timer);
      timer = global.setTimeout(function () {
        saveDraft().catch(function () {});
      }, SAVE_DELAY_MS);
    }

    form.addEventListener("input", queueSave);
    form.addEventListener("change", queueSave);
    form.addEventListener("submit", function () {
      global.clearTimeout(timer);
      removeDraft().catch(function () {});
    });
    global.addEventListener("beforeunload", function () {
      saveDraft().catch(function () {});
    });

    if (restoreButton) {
      restoreButton.addEventListener("click", function () {
        if (pendingPayload) restore(form, pendingPayload);
        if (banner) banner.hidden = true;
      });
    }
    if (discardButton) {
      discardButton.addEventListener("click", function () {
        pendingPayload = null;
        removeDraft().catch(function () {});
      });
    }

    global.SMSOfflineDB.getWizardDraft(key)
      .then(function (row) {
        if (!row || !row.encrypted || Date.now() - Number(row.updated_at || 0) > MAX_AGE_MS) {
          if (row) return removeDraft();
          return null;
        }
        return crypto.decrypt(row.encrypted).then(function (payload) {
          pendingPayload = payload;
          if (banner) banner.hidden = false;
        });
      })
      .catch(function () {});
  }

  function boot() {
    document.querySelectorAll("form[data-rmc-wizard-form]").forEach(bind);
  }

  global.RmcWizardOfflineIntake = { bind: bind, serialize: serialize, restore: restore };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(typeof window !== "undefined" ? window : globalThis);
