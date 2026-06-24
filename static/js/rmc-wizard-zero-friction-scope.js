/**
 * Zero-friction migration scope step — preset one-click apply + live unlock preview.
 * Platform-wide: no per-tenant config. Pairs with wizard_migration_scope_*.html.
 */
(function initWizardZeroFrictionScope() {
  "use strict";

  var root = document.querySelector("[data-rmc-wizard-zf-scope]");
  if (!root) {
    return;
  }

  var UNLOCK_RULES = {
    roster: ["students", "staff"],
    timetable: ["sections"],
    gradebook: ["grades"],
    parent_portal: ["guardians", "students"],
    attendance: ["attendance"],
    billing: ["finance"],
  };

  var UNLOCK_READY = {
    roster: "Ready",
    timetable: "Ready",
    gradebook: "Ready",
    parent_portal: "Ready",
    attendance: "Ready",
    billing: "Ready",
  };

  function selectedDomains() {
    var boxes = root.querySelectorAll("[data-rmc-wizard-zf-checkbox]:checked");
    var out = [];
    for (var i = 0; i < boxes.length; i += 1) {
      out.push(boxes[i].value);
    }
    return out;
  }

  function syncCardSelectedState() {
    var cards = root.querySelectorAll("[data-rmc-wizard-zf-domain-card]");
    for (var i = 0; i < cards.length; i += 1) {
      var card = cards[i];
      var input = card.querySelector("[data-rmc-wizard-zf-checkbox]");
      if (!input) {
        continue;
      }
      card.classList.toggle("rmc-wizard-option-card--selected", input.checked);
    }
  }

  function updateUnlockPreview(domains) {
    var list = document.querySelector("[data-rmc-wizard-zf-unlock-list]");
    if (!list) {
      return;
    }
    var keys = Object.keys(UNLOCK_RULES);
    for (var k = 0; k < keys.length; k += 1) {
      var key = keys[k];
      var item = list.querySelector('[data-rmc-wizard-zf-unlock="' + key + '"]');
      if (!item) {
        continue;
      }
      var required = UNLOCK_RULES[key];
      var ready = true;
      for (var r = 0; r < required.length; r += 1) {
        if (domains.indexOf(required[r]) === -1) {
          ready = false;
          break;
        }
      }
      item.classList.toggle("rmc-wizard-zf-preview__item--ready", ready);
      item.classList.toggle("rmc-wizard-zf-preview__item--muted", !ready);
      var stateEl = item.querySelector("[data-rmc-wizard-zf-unlock-state]");
      if (stateEl && ready) {
        stateEl.textContent = UNLOCK_READY[key] || "Ready";
      }
    }
  }

  function setStatus(message) {
    var status = root.querySelector("[data-rmc-wizard-zf-status]");
    if (!status) {
      return;
    }
    if (!message) {
      status.hidden = true;
      status.textContent = "";
      return;
    }
    status.hidden = false;
    status.textContent = message;
  }

  function applyDomains(domains, statusMessage) {
    var domainSet = {};
    for (var i = 0; i < domains.length; i += 1) {
      domainSet[domains[i]] = true;
    }
    var boxes = root.querySelectorAll("[data-rmc-wizard-zf-checkbox]");
    for (var b = 0; b < boxes.length; b += 1) {
      boxes[b].checked = !!domainSet[boxes[b].value];
    }
    syncCardSelectedState();
    updateUnlockPreview(selectedDomains());
    setStatus(statusMessage || "");

    var presets = root.querySelectorAll("[data-rmc-wizard-zf-preset]");
    for (var p = 0; p < presets.length; p += 1) {
      var presetDomains = (presets[p].getAttribute("data-rmc-wizard-zf-domains") || "")
        .split(",")
        .filter(Boolean)
        .sort()
        .join(",");
      var applied = domains.slice().sort().join(",");
      presets[p].setAttribute("aria-pressed", presetDomains === applied ? "true" : "false");
    }
  }

  root.addEventListener("change", function onCheckboxChange(evt) {
    if (!evt.target || !evt.target.matches("[data-rmc-wizard-zf-checkbox]")) {
      return;
    }
    syncCardSelectedState();
    updateUnlockPreview(selectedDomains());
    setStatus("");
  });

  root.addEventListener("click", function onPresetClick(evt) {
    var btn = evt.target && evt.target.closest("[data-rmc-wizard-zf-preset]");
    if (!btn) {
      return;
    }
    evt.preventDefault();
    var raw = btn.getAttribute("data-rmc-wizard-zf-domains") || "";
    var domains = raw.split(",").map(function trim(v) {
      return v.trim();
    }).filter(Boolean);
    applyDomains(domains, btn.querySelector("strong")
      ? btn.querySelector("strong").textContent + " applied"
      : "Preset applied");
  });

  var actionStack = document.querySelector("[data-rmc-wizard-zf-actions]");
  if (actionStack) {
    actionStack.addEventListener("click", function onActionClick(evt) {
      var applyBtn = evt.target && evt.target.closest("[data-rmc-wizard-zf-apply-preset]");
      if (!applyBtn) {
        return;
      }
      evt.preventDefault();
      var presetKey = applyBtn.getAttribute("data-rmc-wizard-zf-apply-preset");
      var presetBtn = root.querySelector('[data-rmc-wizard-zf-preset="' + presetKey + '"]');
      if (presetBtn) {
        presetBtn.click();
      }
    });
  }

  syncCardSelectedState();
  updateUnlockPreview(selectedDomains());
})();
