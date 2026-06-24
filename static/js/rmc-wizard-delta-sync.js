/* Debounced server draft sync for Setup Studio wizards (survives device loss). */
(function (global) {
  "use strict";

  var SAVE_DELAY_MS = 500;

  function csrfToken(form) {
    var input = form.querySelector('[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function serializeFields(form) {
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
    return fields;
  }

  function bind(form) {
    if (!form || !form.hasAttribute("data-rmc-wizard-form")) return;
    var syncUrl = form.getAttribute("data-rmc-wizard-draft-sync-url");
    if (!syncUrl) return;
    var timer = null;
    var inflight = null;

    function pushDraft() {
      if (inflight && typeof inflight.abort === "function") {
        inflight.abort();
      }
      var controller = global.AbortController ? new global.AbortController() : null;
      inflight = controller;
      var headers = {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(form),
        "X-Requested-With": "XMLHttpRequest",
      };
      var options = {
        method: "POST",
        credentials: "same-origin",
        headers: headers,
        body: JSON.stringify({ fields: serializeFields(form) }),
      };
      if (controller) options.signal = controller.signal;
      global.fetch(syncUrl, options).then(function (response) {
        if (!response.ok) return null;
        return response.json();
      }).then(function (payload) {
        if (!payload || payload.status !== "saved") return;
        form.setAttribute("data-rmc-wizard-draft-synced", "1");
        form.dispatchEvent(new CustomEvent("rmc:wizard-draft-saved", { bubbles: true }));
      }).catch(function () {
        /* silent - offline intake still holds local draft */
      });
    }

    function schedule() {
      if (timer) global.clearTimeout(timer);
      timer = global.setTimeout(pushDraft, SAVE_DELAY_MS);
    }

    form.addEventListener("input", schedule);
    form.addEventListener("change", schedule);
  }

  function init() {
    document.querySelectorAll("form[data-rmc-wizard-form]").forEach(bind);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
