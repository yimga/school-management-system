    (function () {
      const viewSelect = document.getElementById("id_dashboard_view");
      const widgetRow = document.getElementById("id_dashboard_widgets")?.closest(".mb-3");
      const timezoneSelect = document.getElementById("id_timezone");

      const toggleWidgets = () => {
        if (!viewSelect || !widgetRow) return;
        widgetRow.style.display = viewSelect.value === "CUSTOM" ? "block" : "none";
      };
      if (viewSelect && widgetRow) {
        viewSelect.addEventListener("change", toggleWidgets);
        toggleWidgets();
      }

      // Default to browser timezone when available
      if (timezoneSelect) {
        const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
        const hasOption = Array.from(timezoneSelect.options || []).some((opt) => opt.value === browserTz);
        if (hasOption && !timezoneSelect.value) {
          timezoneSelect.value = browserTz;
        }
      }

      const form = document.getElementById("user-preferences-form");
      const submitBtn = document.getElementById("preferences-submit-btn");
      if (form && submitBtn) {
        form.addEventListener("submit", function () {
          submitBtn.disabled = true;
          submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Saving…';
        });
      }
    })();
  
