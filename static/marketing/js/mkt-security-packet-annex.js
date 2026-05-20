(function () {
  var dataEl = document.getElementById("mkt-security-annex-data");
  if (!dataEl) return;
  var annexByJurisdiction;
  try {
    annexByJurisdiction = JSON.parse(dataEl.textContent || "{}");
  } catch (e) {
    return;
  }
  var previewSelect = document.querySelector("[data-mkt-security-jurisdiction-preview]");
  var formSelect = document.querySelector("[data-mkt-security-jurisdiction-form]");
  var profileInput = document.getElementById("sp_compliance_profile_id");
  var section = document.querySelector("[data-mkt-security-country-annex]");
  if (!section || !previewSelect) return;

  function applyAnnex(annex) {
    if (!annex) return;
    var map = {
      "annex-country-code": annex.country_code || "—",
      "annex-profile-name": annex.profile_name || "",
      "annex-currency": annex.currency_code || "",
      "annex-timezone": annex.timezone || "",
      "annex-retention": annex.retention_summary || "",
      "annex-calendar": annex.calendar_note || "",
      "annex-residency": annex.data_residency_note || "",
    };
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = map[id];
    });
    var profileEl = document.getElementById("annex-profile-id");
    if (profileEl) {
      profileEl.innerHTML = annex.compliance_profile_id
        ? "<code>" + annex.compliance_profile_id + "</code>"
        : "—";
    }
    if (profileInput) profileInput.value = annex.compliance_profile_id || "";
  }

  function onJurisdictionChange(value) {
    applyAnnex(annexByJurisdiction[value] || annexByJurisdiction[""]);
    if (formSelect && value) formSelect.value = value;
  }

  previewSelect.addEventListener("change", function () {
    onJurisdictionChange(previewSelect.value);
  });
  if (formSelect) {
    formSelect.addEventListener("change", function () {
      previewSelect.value = formSelect.value;
      onJurisdictionChange(formSelect.value);
    });
  }
})();
