(function () {
  "use strict";
  var form = document.querySelector("[data-rmc-signup-form]");
  var panel = document.querySelector("[data-rmc-signup-recommendation]");
  if (!form || !panel) return;

  function value(name, fallback) {
    var element = form.elements[name];
    return element && String(element.value || "").trim() || fallback;
  }
  function number(name) { return Math.max(0, parseInt(value(name, "0"), 10) || 0); }
  function set(selector, copy) { var node = panel.querySelector(selector); if (node) node.textContent = copy; }

  function refresh() {
    var scope = value("organization_scope", "single");
    var capacity = number("student_capacity");
    var campuses = number("campus_count") || (scope === "single" ? 1 : 2);
    var staff = number("staff_count");
    var operating = value("operating_model", "day");
    var connectivity = value("connectivity_profile", "mixed");
    var payments = value("payment_profile", "basic");
    var enterprise = scope !== "single" || campuses > 1 || capacity >= 1000 || staff >= 150;
    var operations = operating !== "day" || payments !== "basic" || connectivity === "limited";
    var plan = enterprise ? "Campus Enterprise" : operations ? "School Pro Operations" : "School Pro";
    set("[data-rmc-recommendation-plan]", plan);
    set("[data-rmc-recommendation-copy]", enterprise ? "Governance and analytics sized for a multi-campus or high-volume institution." : operations ? "Extra day-to-day operations for boarding, payments or limited connectivity." : "A balanced school workspace with local-first operations.");
    set("[data-rmc-recommendation-scope]", scope === "single" && campuses <= 1 ? "Single-campus operations" : "Multi-campus governance");
    set("[data-rmc-recommendation-modules]", connectivity === "limited" ? "Offline capture, sync and continuity included" : operating === "boarding" || operating === "mixed" ? "Boarding, welfare and core records" : payments !== "basic" ? "Core records and multi-channel finance" : "Core records, attendance and communication");
  }

  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);
  refresh();
}());
