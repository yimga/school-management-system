(function () {
  "use strict";

  var globalSchool = document.getElementById("app-catalog-global-school");
  var impactSchoolHidden = document.getElementById("rmcInstallImpactSchoolId");

  function selectedSchoolId() {
    return globalSchool && globalSchool.value ? globalSchool.value : "";
  }

  function syncSchoolTargets() {
    var sid = selectedSchoolId();
    if (impactSchoolHidden) impactSchoolHidden.value = sid;
    if (globalSchool && sid) {
      try {
        var url = new URL(window.location.href);
        url.searchParams.set("school_id", sid);
        window.history.replaceState({}, "", url.toString());
      } catch (e) { /* ignore */ }
    }
  }

  function requireSchool() {
    if (selectedSchoolId()) return true;
    if (globalSchool) {
      globalSchool.focus();
      globalSchool.classList.add("is-invalid");
    }
    window.alert("Select a target school at the top of the catalog before installing.");
    return false;
  }

  if (globalSchool) {
    globalSchool.addEventListener("change", function () {
      globalSchool.classList.remove("is-invalid");
      syncSchoolTargets();
    });
    syncSchoolTargets();
  }

  document.querySelectorAll("[data-rmc-open-install-impact]").forEach(function (btn) {
    btn.addEventListener(
      "click",
      function () {
        if (!requireSchool()) return;
        btn.setAttribute("data-school-id", selectedSchoolId());
        syncSchoolTargets();
      },
      true
    );
  });

  var searchEl = document.getElementById("app-catalog-search");
  var listEl = document.getElementById("app-catalog-list");
  if (searchEl && listEl && !searchEl.form) {
    var cards = listEl.querySelectorAll("[data-rmc-mkt-app-card]");
    searchEl.addEventListener("input", function () {
      var q = (searchEl.value || "").trim().toLowerCase();
      cards.forEach(function (card) {
        if (!q) {
          card.style.display = "";
          return;
        }
        var haystack = [
          card.getAttribute("data-app-name") || "",
          card.getAttribute("data-app-slug") || "",
          card.getAttribute("data-app-desc") || "",
        ].join(" ");
        card.style.display = haystack.indexOf(q) >= 0 ? "" : "none";
      });
    });
  }
})();
