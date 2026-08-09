/**
 * Admin OS v15 I11 — per-model policy pack.
 * Applied after DOM ready on change-form surfaces.
 */
(function () {
  "use strict";

  var POLICIES = {
    "accounts.user": { collapseM2mAfterFirst: true },
    "auth.user": { collapseM2mAfterFirst: true },
    // Site Settings keeps the canonical page-aware context rail and tools.
    // Focus mode remains an explicit keyboard choice; it is never forced by a
    // model policy because doing so silently flattens the approved workspace.
    "siteconfig.sitesettings": {},
    "schools.school": { keepIdentityOpen: true },
  };

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function modelKey() {
    var m = document.body.className.match(/\bapp-(\S+)\s+model-(\S+)/);
    if (!m) return "";
    return m[1] + "." + m[2];
  }

  function collapseM2mAfterFirst() {
    var body = document.querySelector("[data-rmc-django-form-body]");
    if (!body) return;
    var panels = body.querySelectorAll("details.rmc-admin-transfer-panel, details.rmc-admin-disclosure");
    Array.prototype.forEach.call(panels, function (panel, i) {
      if (panel.closest(".inline-group")) return;
      if (i === 0) panel.open = true;
      else panel.open = false;
    });
  }

  function enableFocusMode() {
    var ws =
      document.querySelector("[data-rmc-admin-focus-root]") ||
      document.querySelector('[data-rmc-django-workspace="change-form"]');
    if (!ws) return;
    ws.setAttribute("data-rmc-admin-focus", "1");
    try {
      var scope =
        (document.querySelector("[data-rmc-admin-workspace-scope]") &&
          document
            .querySelector("[data-rmc-admin-workspace-scope]")
            .getAttribute("data-rmc-admin-workspace-scope")) ||
        "tenant";
      sessionStorage.setItem("rmc-admin-focus-mode:" + scope, "1");
    } catch (_e) {
      /* ignore */
    }
  }

  function keepIdentitySectionsOpen() {
    var main = document.getElementById("content-main");
    if (!main) return;
    var identityRe = /identity|school\s*name|basic|general|profile/i;
    main.querySelectorAll("fieldset.module, .inline-group, details.rmc-admin-disclosure").forEach(
      function (sec) {
        var h = sec.querySelector("h2, summary, .inline-heading");
        var text = h ? (h.textContent || "") : "";
        if (identityRe.test(text)) {
          if (sec.tagName === "DETAILS") sec.open = true;
          sec.classList.add("rmc-admin-policy-identity-open");
        }
      }
    );
  }

  function apply() {
    var key = modelKey();
    var policy = POLICIES[key];
    if (!policy) return;
    if (policy.collapseM2mAfterFirst) collapseM2mAfterFirst();
    if (policy.defaultFocusMode) enableFocusMode();
    if (policy.keepIdentityOpen) keepIdentitySectionsOpen();
  }

  ready(function () {
    if (document.querySelector('[data-rmc-admin-archetype="edit"]')) {
      apply();
      window.setTimeout(apply, 0);
      window.addEventListener("load", function () {
        window.setTimeout(apply, 0);
      });
    }
  });
})();
