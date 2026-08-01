(function () {
  "use strict";

  function initialiseCatalogFilters() {
    var form = document.querySelector('[data-rmc-catalog-filter-form="1"]');
    if (!form) return;

    var search = form.querySelector("[data-catalog-search-input]");
    var facets = Array.from(form.querySelectorAll("[data-catalog-facet]"));
    var debounce = null;
    var lastSubmitted = new URLSearchParams(new FormData(form)).toString();

    function submitIfChanged() {
      var next = new URLSearchParams(new FormData(form)).toString();
      if (next === lastSubmitted) return;
      lastSubmitted = next;
      form.requestSubmit();
    }

    if (search) {
      search.addEventListener("input", function () {
        window.clearTimeout(debounce);
        debounce = window.setTimeout(submitIfChanged, 320);
      });
      search.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && search.value) {
          event.preventDefault();
          search.value = "";
          window.clearTimeout(debounce);
          submitIfChanged();
        }
      });
    }

    facets.forEach(function (facet) {
      facet.addEventListener("change", function () {
        window.clearTimeout(debounce);
        submitIfChanged();
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiseCatalogFilters);
  } else {
    initialiseCatalogFilters();
  }
}());
