(function () {
  "use strict";

  var form = document.querySelector("[data-rmc-signup-form]");
  var panel = document.querySelector("[data-rmc-signup-recommendation]");
  if (!form || !panel) return;

  var PLAN_LABELS = {
    "school-pro": "School Pro",
    "school-pro-operations": "School Pro Operations",
    "campus-enterprise": "Campus Enterprise"
  };

  function textValue(name, fallback) {
    var control = form.elements[name];
    if (!control) return fallback;
    var raw = typeof control.value === "string" ? control.value.trim() : "";
    return raw || fallback;
  }

  function boundedNumber(name, maximum) {
    var parsed = Number.parseInt(textValue(name, "0"), 10);
    if (!Number.isFinite(parsed)) return 0;
    return Math.min(maximum, Math.max(0, parsed));
  }

  function checkedValues(name) {
    return Array.prototype.slice.call(
      form.querySelectorAll('[name="' + name + '"]:checked')
    ).map(function (node) { return String(node.value || "").trim(); }).filter(Boolean);
  }

  function includes(values, value) {
    return values.indexOf(value) !== -1;
  }

  function write(selector, copy) {
    var node = panel.querySelector(selector);
    if (node) node.textContent = copy;
  }

  function markRecommended(field, recommendedValue) {
    var flags = form.querySelectorAll('[data-rmc-choice-recommended^="' + field + ':"]');
    Array.prototype.forEach.call(flags, function (flag) {
      flag.hidden = flag.getAttribute("data-rmc-choice-recommended") !== field + ":" + recommendedValue;
    });
  }

  function deriveRecommendation() {
    var scope = textValue("organization_scope", "single");
    var scale = textValue("learner_scale", "under-1000");
    var capacity = boundedNumber("student_capacity", 1000000);
    var campuses = boundedNumber("campus_count", 10000) || (scope === "single" ? 1 : 2);
    var staff = boundedNumber("staff_count", 1000000);
    var operating = textValue("operating_model", "day");
    var connectivity = textValue("connectivity_profile", "mixed");
    var payment = textValue("payment_profile", "basic");
    var assessment = textValue("assessment_profile", "country-default");
    var identity = textValue("identity_profile", "password");
    var residency = textValue("data_residency_requirement", "country-default");
    var accessibility = textValue("accessibility_profile", "standard");
    var migration = textValue("migration_complexity", "none");
    var automation = textValue("automation_preference", "balanced");
    var country = textValue("country_code", "").toUpperCase();
    var cycles = checkedValues("school_type");
    var languages = checkedValues("language_codes");
    var services = checkedValues("operational_services");
    var domains = checkedValues("migration_domains");
    var vendor = textValue("migration_vendor", "");

    if ((operating === "boarding" || operating === "mixed") && !includes(services, "boarding")) {
      services.push("boarding");
    }
    if (!capacity) {
      capacity = scale === "5000-plus" ? 5000 : scale === "1000-4999" ? 1500 : 500;
    }

    var multiCampus = scope !== "single" || campuses > 1;
    var enterpriseReasons = [];
    var operationsReasons = [];
    if (multiCampus) enterpriseReasons.push("shared multi-campus governance");
    if (capacity >= 2500 || staff >= 300) enterpriseReasons.push("high operating scale");
    if (residency === "self-hosted") enterpriseReasons.push("self-hosted data residency");
    if (migration === "legacy-high-risk") enterpriseReasons.push("high-risk migration controls");
    if (services.length) operationsReasons.push("specialized daily operations");
    if (payment !== "basic" && payment !== "cash-only") operationsReasons.push("digital or multi-channel finance");
    if (connectivity === "limited" || connectivity === "offline-first") operationsReasons.push("offline-first continuity");
    if (capacity >= 1000 || automation === "automation-first") operationsReasons.push("analytics and automation scale");

    var plan = enterpriseReasons.length ? "campus-enterprise" : operationsReasons.length ? "school-pro-operations" : "school-pro";
    var cycleText = cycles.join(" ").toLowerCase();
    var secondary = /(secondary|high|sss|tvet)/.test(cycleText);
    var blueprint = multiCampus ? "multi-campus-network" :
      (assessment === "international" || assessment === "mixed") ? "international-school" :
      (country === "CM" && secondary) ? "cameroon-gce-school" :
      secondary ? "private-secondary-school" : "private-primary-school";

    var overlays = [];
    if (includes(services, "boarding") && blueprint !== "boarding-school") overlays.push("boarding");
    if ((connectivity === "limited" || connectivity === "offline-first") && blueprint !== "low-connectivity-school") overlays.push("low-connectivity");
    if (languages.length > 1 && blueprint !== "bilingual-school") overlays.push("bilingual");

    var modules = ["core records", "attendance", "family communication"];
    if (multiCampus) modules.push("delegated governance");
    if (capacity >= 1000 || staff >= 150) modules.push("advanced analytics");
    if (services.length) modules.push(services.join(", "));
    if (connectivity === "limited" || connectivity === "offline-first") modules.push("offline sync");
    if (payment === "online" || payment === "multi-channel" || payment === "complex-aid") modules.push("payments and reconciliation");
    if (migration !== "none" || vendor || domains.length) modules.push("guided migration");

    var explicit = [country, cycles.length, languages.length, scope, scale, operating, connectivity]
      .filter(Boolean).length;
    ["funding_type", "student_capacity", "campus_count", "staff_count", "payment_profile", "assessment_profile", "identity_profile", "data_residency_requirement", "accessibility_profile", "migration_complexity", "automation_preference"]
      .forEach(function (name) { if (textValue(name, "")) explicit += 1; });
    var missing = (country ? 0 : 1) + (cycles.length ? 0 : 1) + (textValue("funding_type", "") ? 0 : 1);
    var confidence = Math.min(96, Math.max(35, 48 + explicit * 3 - missing * 9));

    return {
      plan: plan,
      planReason: (enterpriseReasons.length ? enterpriseReasons : operationsReasons.length ? operationsReasons : ["single-school core operations"]).join(", "),
      scope: multiCampus ? "Multi-campus governance and delegated administration" : "Single-campus operations",
      blueprint: blueprint + (overlays.length ? " + " + overlays.join(" + ") : ""),
      modules: modules.join(" · "),
      compliance: ["Country " + (country || "default"), assessment, residency, accessibility].join(" · "),
      confidence: confidence,
      recommended: {
        organization_scope: campuses > 1 ? (scope === "district" ? "district" : "network") : "single",
        learner_scale: capacity >= 5000 ? "5000-plus" : capacity >= 1000 ? "1000-4999" : "under-1000",
        operating_model: includes(services, "boarding") ? (operating === "mixed" ? "mixed" : "boarding") : "day",
        connectivity_profile: connectivity
      }
    };
  }

  function refresh() {
    try {
      var recommendation = deriveRecommendation();
      write("[data-rmc-recommendation-plan]", PLAN_LABELS[recommendation.plan] || recommendation.plan);
      write("[data-rmc-recommendation-copy]", recommendation.planReason + ". Review the recommendation before provisioning.");
      write("[data-rmc-recommendation-blueprint]", recommendation.blueprint);
      write("[data-rmc-recommendation-scope]", recommendation.scope);
      write("[data-rmc-recommendation-modules]", recommendation.modules);
      write("[data-rmc-recommendation-compliance]", recommendation.compliance);
      write("[data-rmc-recommendation-confidence]", recommendation.confidence + "% confidence from the answers supplied");
      var bar = panel.querySelector("[data-rmc-recommendation-confidence-bar]");
      if (bar) bar.style.inlineSize = recommendation.confidence + "%";
      Object.keys(recommendation.recommended).forEach(function (field) {
        markRecommended(field, recommendation.recommended[field]);
      });
      panel.setAttribute("data-rmc-recommendation-preview-ready", "true");
      panel.removeAttribute("data-rmc-recommendation-preview-error");
    } catch (error) {
      panel.setAttribute("data-rmc-recommendation-preview-error", "true");
      write("[data-rmc-recommendation-copy]", "We could not refresh the preview. Your answers are still safe; submit to run the server-side recommendation checks.");
    }
  }

  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);
  refresh();
}());
