(function () {
  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
      return;
    }
    fn();
  }

  function wireMonthSelector() {
    var monthSelect = document.getElementById("super-month-select");
    if (!monthSelect) return;
    monthSelect.addEventListener("change", function () {
      var form = document.getElementById("super-month-form");
      if (form) form.submit();
    });
  }

  function wireSchoolFilters() {
    var searchInput = document.getElementById("cp-school-search");
    var stateFilter = document.getElementById("cp-school-filter");
    var rows = Array.prototype.slice.call(document.querySelectorAll(".cp-school-row"));
    var visibleCounter = document.getElementById("cp-visible-school-count");
    if (!rows.length || !searchInput || !stateFilter) return;

    function apply() {
      var query = String(searchInput.value || "").toLowerCase().trim();
      var state = String(stateFilter.value || "all").toLowerCase();
      var visible = 0;

      rows.forEach(function (row) {
        var haystack = String(row.getAttribute("data-search") || "");
        var rowState = String(row.getAttribute("data-state") || "healthy").toLowerCase();
        var matchesQuery = !query || haystack.indexOf(query) >= 0;
        var matchesState = state === "all" || rowState === state;
        var show = matchesQuery && matchesState;
        row.classList.toggle("is-hidden", !show);
        if (show) visible += 1;
      });

      if (visibleCounter) {
        visibleCounter.textContent = String(visible);
      }
    }

    searchInput.addEventListener("input", apply);
    stateFilter.addEventListener("change", apply);
    apply();
  }

  function wireApprovalButtons() {
    var buttons = Array.prototype.slice.call(document.querySelectorAll(".approve-btn"));
    if (!buttons.length) return;

    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        if (!window.confirm("Approve this school?")) return;
        var schoolId = this.getAttribute("data-school-id");
        var csrfToken = this.getAttribute("data-csrftoken");
        if (!schoolId || !csrfToken) return;

        var url = "/super/api/schools/" + schoolId + "/approve/";
        fetch(url, {
          method: "POST",
          headers: {
            "X-CSRFToken": csrfToken,
            "Content-Type": "application/json"
          },
          body: "{}",
          credentials: "same-origin"
        })
          .then(function (response) {
            if (response.ok) {
              window.location.reload();
              return null;
            }
            return response.json().then(function (payload) {
              throw new Error(payload.error || "Approval failed");
            });
          })
          .catch(function (error) {
            window.alert(error.message || "Approval failed");
          });
      });
    });
  }

  onReady(function () {
    wireMonthSelector();
    wireSchoolFilters();
    wireApprovalButtons();
  });
})();
