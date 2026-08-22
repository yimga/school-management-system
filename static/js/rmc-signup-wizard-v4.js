(function () {
  "use strict";

  var form = document.querySelector("[data-rmc-signup-wizard]");
  if (!form || form.dataset.rmcWizardReady === "1") return;
  form.dataset.rmcWizardReady = "1";

  var current = 1;
  var total = 5;
  var panels = [];
  var status;
  var review;
  var draftTimer;
  var recommendationTimer;
  var queuedSubmission = false;
  var STEP_GUIDANCE = {
    1: ["Reserve your workspace", "Country choices preload local calendars and terminology.", "Only school name, country and admin email are required."],
    2: ["Shape the right setup", "Your answers tune modules, blueprint and offline defaults.", "Every recommendation remains reviewable before launch."],
    3: ["Match local education", "Languages, cycles and grading vocabulary follow your region.", "Choose every education cycle your school currently serves."],
    4: ["Start clean or migrate", "Import choices prepare the Migration Cloud without blocking signup.", "You can skip migration and connect data after verification."],
    5: ["You remain in control", "Nothing is provisioned until you confirm this review.", "Recommendations include evidence, confidence and alternatives."]
  };

  function directField(name) {
    return form.querySelector(':scope > [data-rmc-signup-field="' + name + '"]');
  }

  function makePanel(number, title, copy) {
    var panel = document.createElement("section");
    panel.className = "rmc-signup-wizard-panel";
    panel.dataset.rmcWizardPanel = String(number);
    panel.setAttribute("aria-labelledby", "rmc-signup-step-title-" + number);
    var guidance = STEP_GUIDANCE[number];
    panel.innerHTML = '<header class="rmc-signup-wizard-panel__header">' +
      '<div><span>Step ' + number + ' of ' + total + '</span>' +
      '<h2 id="rmc-signup-step-title-' + number + '">' + title + '</h2>' +
      '<p>' + copy + '</p></div><small>Progress saves locally</small></header>' +
      '<div class="rmc-signup-wizard-panel__workspace">' +
      '<div class="rmc-signup-wizard-panel__body"></div>' +
      '<aside class="rmc-signup-wizard-guide" aria-label="Step guidance">' +
      '<span class="rmc-signup-wizard-guide__eyebrow">Recommended path</span>' +
      '<strong>' + guidance[0] + '</strong><p>' + guidance[1] + '</p>' +
      '<div class="rmc-signup-wizard-guide__note"><i aria-hidden="true">✓</i><span>' + guidance[2] + '</span></div>' +
      '<div class="rmc-signup-wizard-guide__completion" data-rmc-step-completion>Ready to begin</div>' +
      '</aside></div>';
    form.appendChild(panel);
    panels[number] = panel;
    return panel.querySelector(".rmc-signup-wizard-panel__body");
  }

  function move(node, body) {
    if (node) body.appendChild(node);
  }

  function size(node, value) {
    if (node) node.dataset.rmcWizardWidth = value;
    return node;
  }

  function controlsFor(panel) {
    return Array.prototype.slice.call(panel.querySelectorAll("input,select,textarea"))
      .filter(function (node) { return node.type !== "hidden" && !node.disabled; });
  }

  function createWizard() {
    var submit = form.querySelector(':scope > [data-rmc-signup-submit]');
    var countryRow = form.querySelector(":scope > .row");
    var identity = makePanel(1, "School identity", "The essentials needed to reserve and verify your workspace.");
    move(size(directField("name"), "wide"), identity);
    move(size(directField("slug"), "standard"), identity);
    move(size(directField("email"), "wide"), identity);
    if (countryRow) countryRow.classList.add("rmc-signup-identity-locality");
    move(size(countryRow, "standard"), identity);

    var operations = makePanel(2, "How will this school operate?", "Only decisions that materially change your setup are shown.");
    move(directField("institution_profile"), operations);

    var education = makePanel(3, "Education and local context", "Confirm languages, education cycles and country-matched terminology.");
    move(size(directField("language"), "standard"), education);
    move(size(directField("school_type"), "wide"), education);

    var launch = makePanel(4, "Data and launch", "Tell us what should be ready on day one. You can safely start fresh.");
    move(size(directField("migration_vendor"), "standard"), launch);
    move(size(directField("migration_domains"), "wide"), launch);

    var finalBody = makePanel(5, "Review before anything is applied", "Compare the recommendation, evidence and alternatives. You remain in control.");
    review = document.createElement("div");
    review.className = "rmc-signup-review";
    review.dataset.rmcSignupReview = "1";
    finalBody.appendChild(review);
    if (submit) finalBody.appendChild(submit);

    status = document.createElement("div");
    status.className = "rmc-signup-draft-status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    form.prepend(status);

    panels.slice(1).forEach(function (panel, index) {
      var actions = document.createElement("div");
      actions.className = "rmc-signup-wizard-actions";
      if (index > 0) actions.innerHTML += '<button type="button" class="btn btn-outline-secondary" data-rmc-wizard-back>Back</button>';
      if (index < total - 1) actions.innerHTML += '<button type="button" class="btn btn-primary" data-rmc-wizard-next>Continue</button>';
      panel.appendChild(actions);
    });
  }

  function setStep(next, focus) {
    var previous = current;
    current = Math.min(total, Math.max(1, next));
    panels.slice(1).forEach(function (panel, index) {
      var active = index + 1 === current;
      panel.hidden = !active;
      panel.setAttribute("aria-hidden", active ? "false" : "true");
    });
    document.querySelectorAll("[data-rmc-wizard-step-indicator]").forEach(function (item) {
      var step = Number(item.dataset.rmcWizardStepIndicator);
      item.toggleAttribute("aria-current", step === current);
      item.classList.toggle("rmc-signup-progress--done", step < current);
    });
    if (current === total) renderReview();
    updateCompletion(panels[current]);
    try {
      sessionStorage.setItem("rmc-signup-current-step", String(current));
    } catch (_storageError) {
      /* A privacy-restricted browser can deny storage; the server form remains usable. */
    }
    emitJourney(current, current > previous ? "continue" : current < previous ? "back" : "view");
    if (focus) panels[current].querySelector("h2").focus({ preventScroll: true });
    panels[current].scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  function updateCompletion(panel) {
    if (!panel) return;
    var controls = controlsFor(panel).filter(function (node) { return node.type !== "radio" || node.checked; });
    var meaningful = controls.filter(function (node) {
      return (node.type === "checkbox" || node.type === "radio") ? node.checked : String(node.value || "").trim();
    });
    var required = controlsFor(panel).filter(function (node) { return node.required; });
    var validRequired = required.filter(function (node) { return node.checkValidity(); });
    var output = panel.querySelector("[data-rmc-step-completion]");
    if (!output) return;
    output.textContent = required.length && validRequired.length < required.length
      ? validRequired.length + " of " + required.length + " essentials ready"
      : meaningful.length ? "Step is ready to continue" : "Optional choices can be skipped";
    output.classList.toggle("is-ready", !required.length || validRequired.length === required.length);
  }

  function validatePanel(panel) {
    var invalid = controlsFor(panel).find(function (control) { return !control.checkValidity(); });
    if (!invalid) return true;
    invalid.reportValidity();
    invalid.focus();
    return false;
  }

  function selectedText(name) {
    var node = form.querySelector('[name="' + name + '"]:checked') || form.elements[name];
    if (!node) return "Not provided";
    if (node.tagName === "SELECT") return node.options[node.selectedIndex] ? node.options[node.selectedIndex].text.trim() : "Not provided";
    return (node.closest("label") && node.closest("label").innerText.trim().split("\n")[0]) || node.value || "Not provided";
  }

  function renderReview() {
    if (!review) return;
    review.innerHTML = '<div><small>School</small><strong>' + escapeText((form.elements.name && form.elements.name.value) || "Not provided") + '</strong></div>' +
      '<div><small>Country</small><strong>' + escapeText(selectedText("country_code")) + '</strong></div>' +
      '<div><small>Campus structure</small><strong>' + escapeText(selectedText("organization_scope")) + '</strong></div>' +
      '<div><small>Connectivity</small><strong>' + escapeText(selectedText("connectivity_profile")) + '</strong></div>' +
      '<div><small>Education</small><strong>' + escapeText(checkedLabels("school_type") || "Confirm during setup") + '</strong></div>' +
      '<div><small>Migration</small><strong>' + escapeText(selectedText("migration_vendor")) + '</strong></div>';
  }

  function checkedLabels(name) {
    return Array.prototype.slice.call(form.querySelectorAll('[name="' + name + '"]:checked')).map(function (node) {
      return (node.closest("label") && node.closest("label").innerText.trim().split("\n")[0]) || node.value;
    }).join(", ");
  }

  function escapeText(value) {
    var div = document.createElement("div");
    div.textContent = String(value || "");
    return div.innerHTML;
  }

  function recommendationParams() {
    var params = new URLSearchParams();
    new FormData(form).forEach(function (value, key) {
      if (key !== "csrfmiddlewaretoken" && key !== "email" && String(value).length < 256) params.append(key, String(value));
    });
    return params;
  }

  function updateRecommendation(payload) {
    var envelope = payload.confidence || {};
    var score = Number(envelope.overall_score || 0);
    var panel = form.querySelector("[data-rmc-signup-recommendation]");
    if (!panel) return;
    var label = panel.querySelector("[data-rmc-recommendation-confidence]");
    var bar = panel.querySelector("[data-rmc-recommendation-confidence-bar]");
    var next = panel.querySelector("[data-rmc-confidence-next]");
    var breakdown = panel.querySelector("[data-rmc-confidence-breakdown]");
    if (label) label.textContent = score + "% recommendation readiness · " + String(envelope.label_display || envelope.label || "provisional").replaceAll("-", " ");
    if (bar) bar.style.inlineSize = score + "%";
    if (next) {
      // Server-supplied WORDS (translated). `missing_critical_evidence` is the
      // machine list and stays untouched; rendering it was the bug.
      var missing = envelope.missing_critical_evidence_labels || [];
      next.hidden = !missing.length;
      next.textContent = missing.length ? "To improve confidence, confirm: " + missing.join("; ") + "." : "All critical evidence is confirmed.";
    }
    if (breakdown) {
      breakdown.hidden = false;
      breakdown.innerHTML = Object.keys(envelope.components || {}).map(function (key) {
        return '<span><small>' + escapeText(key.replaceAll("_", " ")) + '</small><b>' + Number(envelope.components[key]) + '%</b></span>';
      }).join("");
    }
    var recs = payload.recommendations || {};
    var plan = panel.querySelector("[data-rmc-recommendation-plan]");
    if (plan && recs.subscription_plan) plan.textContent = String(recs.subscription_plan).replaceAll("-", " ");
    var alternatives = panel.querySelector("[data-rmc-recommendation-alternatives-body]");
    if (alternatives) {
      var planCard = (payload.cards || []).find(function (card) { return card.key === "subscription_plan"; });
      var choices = planCard && planCard.alternatives && planCard.alternatives.length ? planCard.alternatives : ["school-pro", "school-pro-operations", "campus-enterprise"];
      alternatives.textContent = "Compare: " + choices.join(" · ").replaceAll("-", " ") + ". Engine " + (payload.engine || "local rules") + ", fingerprint " + (payload.fingerprint || "pending") + ".";
    }
    var issues = payload.validation_issues || [];
    panel.querySelectorAll("[data-rmc-confidence-issue]").forEach(function (node) { node.remove(); });
    if (issues.length) {
      var issueBox = document.createElement("div");
      issueBox.dataset.rmcConfidenceIssue = "1";
      issueBox.className = "rmc-signup-confidence-next";
      issueBox.textContent = "Resolve before high confidence: " + issues.map(function (issue) { return issue.message || String(issue.code || "").replaceAll("_", " "); }).join(" · ");
      panel.appendChild(issueBox);
    }
    panel.dataset.rmcConfidenceEligible = envelope.high_confidence_eligible ? "true" : "false";
  }

  function refreshRecommendation() {
    var url = form.dataset.rmcRecommendationsUrl;
    if (!url || !navigator.onLine) return;
    clearTimeout(recommendationTimer);
    recommendationTimer = setTimeout(function () {
      fetch(url + "?" + recommendationParams().toString(), { headers: { Accept: "application/json" }, credentials: "same-origin" })
        .then(function (response) { if (!response.ok) throw new Error("preview"); return response.json(); })
        .then(updateRecommendation)
        .catch(function () { status.textContent = "Local recommendations remain available; online evidence refresh is waiting."; });
    }, 280);
  }

  function csrfToken() {
    var node = form.querySelector('[name="csrfmiddlewaretoken"]');
    return node ? node.value : "";
  }

  function emitJourney(stage, action) {
    var url = form.dataset.rmcJourneyEventUrl;
    if (!url || !navigator.onLine) return;
    var body = new URLSearchParams({ stage: String(stage), action: action });
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: { "Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": csrfToken(), Accept: "application/json" },
      body: body.toString()
    }).catch(function () {});
  }

  function openDraftDatabase() {
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open("rmc-signup-drafts", 1);
      request.onupgradeneeded = function () {
        var db = request.result;
        if (!db.objectStoreNames.contains("vault")) db.createObjectStore("vault");
      };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }

  function dbGet(db, key) {
    return new Promise(function (resolve, reject) {
      var request = db.transaction("vault").objectStore("vault").get(key);
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }

  function dbPut(db, key, value) {
    return new Promise(function (resolve, reject) {
      var request = db.transaction("vault", "readwrite").objectStore("vault").put(value, key);
      request.onsuccess = function () { resolve(); };
      request.onerror = function () { reject(request.error); };
    });
  }

  async function vaultKey(db) {
    var key = await dbGet(db, "key");
    if (key) return key;
    key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
    await dbPut(db, "key", key);
    return key;
  }

  async function saveDraft(pendingSubmit) {
    if (!window.indexedDB || !window.crypto || !crypto.subtle) {
      status.textContent = "Secure device drafts are unavailable in this browser; keep this page open or continue online.";
      return;
    }
    var data = {};
    new FormData(form).forEach(function (value, key) {
      if (key === "csrfmiddlewaretoken" || key === "email") return;
      if (data[key]) data[key] = [].concat(data[key], String(value));
      else data[key] = String(value);
    });
    var db = await openDraftDatabase();
    var key = await vaultKey(db);
    var iv = crypto.getRandomValues(new Uint8Array(12));
    var encoded = new TextEncoder().encode(JSON.stringify({ data: data, step: current, saved_at: Date.now(), pending_submit: Boolean(pendingSubmit) }));
    var cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv: iv }, key, encoded);
    await dbPut(db, "draft", { iv: Array.from(iv), cipher: Array.from(new Uint8Array(cipher)) });
    status.textContent = navigator.onLine ? "Encrypted draft saved on this device." : "Offline · encrypted draft saved and ready to continue.";
    if (!navigator.onLine) emitJourney(current, pendingSubmit ? "submit-queued" : "offline-save");
  }

  async function restoreDraft() {
    if (!window.indexedDB || !window.crypto || !crypto.subtle) {
      status.textContent = "Secure device drafts are unavailable in this browser; the online signup remains available.";
      return;
    }
    try {
      var db = await openDraftDatabase();
      var sealed = await dbGet(db, "draft");
      if (!sealed) return;
      var key = await vaultKey(db);
      var plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: new Uint8Array(sealed.iv) }, key, new Uint8Array(sealed.cipher));
      var draft = JSON.parse(new TextDecoder().decode(plain));
      Object.keys(draft.data || {}).forEach(function (name) {
        var values = [].concat(draft.data[name]);
        form.querySelectorAll('[name="' + CSS.escape(name) + '"]').forEach(function (node) {
          if (node.type === "checkbox" || node.type === "radio") node.checked = values.indexOf(node.value) >= 0;
          else if (values[0] && !node.value) node.value = values[0];
        });
      });
      current = Math.min(total, Math.max(1, Number(draft.step || 1)));
      queuedSubmission = Boolean(draft.pending_submit);
      status.textContent = "Encrypted draft restored from this device.";
    } catch (_error) {
      status.textContent = "A local draft could not be opened. Your online signup remains unchanged.";
    }
  }

  createWizard();
  form.addEventListener("click", function (event) {
    if (event.target.closest("[data-rmc-wizard-next]")) {
      if (validatePanel(panels[current])) setStep(current + 1, true);
    }
    if (event.target.closest("[data-rmc-wizard-back]")) setStep(current - 1, true);
  });
  form.addEventListener("input", function () {
    updateCompletion(panels[current]);
    clearTimeout(draftTimer);
    draftTimer = setTimeout(function () { saveDraft().catch(function () {}); }, 450);
    refreshRecommendation();
  });
  form.addEventListener("change", function () {
    updateCompletion(panels[current]);
    refreshRecommendation();
  });
  form.addEventListener("submit", function (event) {
    if (!navigator.onLine) {
      event.preventDefault();
      queuedSubmission = true;
      saveDraft(true).catch(function () {});
      status.textContent = "You are offline. Submission is queued securely and will resume after reconnection.";
      return;
    }
    var invalidStep = panels.slice(1).findIndex(function (panel) {
      return controlsFor(panel).some(function (control) { return !control.checkValidity(); });
    });
    if (invalidStep >= 0) {
      event.preventDefault();
      setStep(invalidStep + 1, false);
      validatePanel(panels[invalidStep + 1]);
    }
  });
  window.addEventListener("online", function () {
    status.textContent = queuedSubmission ? "Back online · resuming your queued submission." : "Back online · review and submit when ready.";
    if (queuedSubmission) emitJourney(current, "submit-queued");
    emitJourney(current, "offline-recovered");
    refreshRecommendation();
    if (queuedSubmission) {
      queuedSubmission = false;
      setStep(total, false);
      if (validatePanel(panels[total])) form.requestSubmit();
    }
  });
  window.addEventListener("offline", function () { status.textContent = "Offline · changes continue saving securely on this device."; });
  restoreDraft().finally(function () {
    setStep(current, false);
    refreshRecommendation();
  });
}());
