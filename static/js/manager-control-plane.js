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

  function wireSchoolRegistryFilters() {
    var form = document.getElementById("cp-registry-filter-form");
    var searchInput = document.getElementById("cp-school-search");
    var stateFilter = document.getElementById("cp-school-filter");
    if (!form || !searchInput || !stateFilter) return;

    var debounceTimer = null;
    function submitRegistry(resetPage) {
      if (resetPage) {
        var pageInput = form.querySelector('input[name="page"]');
        if (pageInput) pageInput.value = "1";
      }
      form.submit();
    }

    searchInput.addEventListener("input", function () {
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(function () {
        submitRegistry(true);
      }, 400);
    });
    stateFilter.addEventListener("change", function () {
      submitRegistry(true);
    });
    form.addEventListener("submit", function () {
      var pageInput = form.querySelector('input[name="page"]');
      if (pageInput && document.activeElement === searchInput) {
        pageInput.value = "1";
      }
    });
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
    wireSchoolRegistryFilters();
    wireApprovalButtons();
  });
})();
