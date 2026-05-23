/* rmc-template-marketplace.js
 *
 * Tenant template marketplace progressive enhancement.
 * CSP-safe: no inline handlers, no eval, no innerHTML on untrusted content.
 * Idempotent: re-running the bootstrap (HTMX swap, Turbo navigate) is safe.
 */

(function () {
  "use strict";

  function init(scope) {
    if (!scope) {
      scope = document;
    }
    if (scope.dataset && scope.dataset.rmcTemplateMarketplaceInited === "1") {
      return;
    }
    if (scope.dataset) {
      scope.dataset.rmcTemplateMarketplaceInited = "1";
    }
    wireApplyConfirm(scope);
    wireFilterAutoSubmit(scope);
  }

  function wireApplyConfirm(scope) {
    var forms = scope.querySelectorAll("[data-rmc-template-apply-form]");
    forms.forEach(function (form) {
      if (form.dataset.rmcApplyInited === "1") {
        return;
      }
      form.dataset.rmcApplyInited = "1";
      form.addEventListener("submit", function (event) {
        var submitter = event.submitter;
        if (!submitter) {
          return;
        }
        var prompt = submitter.getAttribute("data-rmc-confirm") || "";
        if (!prompt) {
          return;
        }
        var ok = window.confirm(prompt);
        if (!ok) {
          event.preventDefault();
          event.stopPropagation();
        }
      });
    });
  }

  function wireFilterAutoSubmit(scope) {
    var forms = scope.querySelectorAll("[data-rmc-template-filter-form]");
    forms.forEach(function (form) {
      if (form.dataset.rmcFilterInited === "1") {
        return;
      }
      form.dataset.rmcFilterInited = "1";
      var selects = form.querySelectorAll("select");
      selects.forEach(function (sel) {
        sel.addEventListener("change", function () {
          form.submit();
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      init(document);
    });
  } else {
    init(document);
  }

  if (typeof window !== "undefined") {
    window.RMCTemplateMarketplace = { init: init };
  }
})();
