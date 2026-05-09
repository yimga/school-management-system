(function () {
  var searchEl = document.getElementById("app-catalog-search");
  var listEl = document.getElementById("app-catalog-list");
  if (!searchEl || !listEl) return;
  var rows = listEl.querySelectorAll(".proof-app-card[data-app-name]");
  function filter() {
    var q = (searchEl.value || "").trim().toLowerCase();
    rows.forEach(function (row) {
      if (!q) {
        row.style.display = "";
        return;
      }
      var haystack = [
        row.getAttribute("data-app-name") || "",
        row.getAttribute("data-app-slug") || "",
        row.getAttribute("data-app-desc") || ""
      ].join(" ").toLowerCase();
      row.style.display = haystack.indexOf(q) >= 0 ? "" : "none";
    });
  }
  searchEl.addEventListener("input", filter);
  searchEl.addEventListener("search", filter);
})();
