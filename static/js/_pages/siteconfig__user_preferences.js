(function () {
  var viewSelect = document.getElementById("id_dashboard_view");
  var widgetRow = document.getElementById("id_dashboard_widgets")?.closest(".mb-3");
  var timezoneSelect = document.getElementById("id_timezone");
  var langSelect = document.getElementById("id_preferred_language");
  var regionSelect = document.getElementById("id_preferred_region");
  var previewText = document.querySelector("[data-rmc-prefs-preview-text]");

  var pageData = {};
  var dataEl = document.getElementById("page-data-rmc-user-preferences");
  if (dataEl) {
    try {
      pageData = JSON.parse(dataEl.textContent || "{}");
    } catch (_e) {
      pageData = {};
    }
  }

  function toggleWidgets() {
    if (!viewSelect || !widgetRow) return;
    widgetRow.style.display = viewSelect.value === "CUSTOM" ? "block" : "none";
  }

  if (viewSelect && widgetRow) {
    viewSelect.addEventListener("change", toggleWidgets);
    toggleWidgets();
  }

  if (timezoneSelect) {
    var browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    var hasOption = Array.from(timezoneSelect.options || []).some(function (opt) {
      return opt.value === browserTz;
    });
    if (hasOption && !timezoneSelect.value) {
      timezoneSelect.value = browserTz;
    }
  }

  function selectedLabel(select) {
    if (!select || select.selectedIndex < 0) return "";
    var opt = select.options[select.selectedIndex];
    return opt ? (opt.textContent || "").trim() : "";
  }

  function updateLocalePreview() {
    if (!previewText) return;
    var regionCode = regionSelect ? regionSelect.value : "";
    var hints = pageData.regionHints || {};
    var regionHint = hints[regionCode] || hints[""] || "";
    var langLabel = selectedLabel(langSelect);
    var parts = [];
    if (langLabel) {
      parts.push((pageData.languageLabel || "UI language") + ": " + langLabel);
    }
    if (regionHint) {
      parts.push(regionHint);
    }
    previewText.textContent =
      parts.join(" · ") || "Select a region to see date and number formatting.";
  }

  if (langSelect) {
    langSelect.addEventListener("change", updateLocalePreview);
    if (!langSelect.value && langSelect.options.length) {
      langSelect.selectedIndex = 0;
    }
  }
  if (regionSelect) {
    regionSelect.addEventListener("change", updateLocalePreview);
    if (!regionSelect.value && regionSelect.options.length) {
      regionSelect.selectedIndex = 0;
    }
  }
  updateLocalePreview();

  var form = document.getElementById("user-preferences-form");
  var submitBtn = document.getElementById("preferences-submit-btn");
  if (form && submitBtn) {
    form.addEventListener("submit", function () {
      submitBtn.disabled = true;
      submitBtn.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Saving…';
    });
  }
})();
