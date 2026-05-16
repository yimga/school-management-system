// Lexicon Settings — live preview + filter. CSP-clean (no inline <script>).
(function () {
  "use strict";
  function init() {
    var search = document.getElementById("lexicon-search");
    if (search) {
      search.addEventListener("input", function () {
        var query = search.value.trim().toLowerCase();
        var rows = document.querySelectorAll("[data-rmc-lexicon-row]");
        rows.forEach(function (row) {
          var hay = row.getAttribute("data-search-text") || "";
          row.style.display = (!query || hay.indexOf(query) !== -1) ? "" : "none";
        });
      });
    }
    function updatePreview(input) {
      var key = input.getAttribute("data-key");
      var slot = input.getAttribute("data-rmc-lexicon-input");
      var value = (input.value || "").trim() || input.getAttribute("data-default") || "";
      var target = document.querySelector("[data-rmc-lexicon-preview-" + slot + "='" + key + "']");
      if (target) target.textContent = value;
    }
    document.querySelectorAll("[data-rmc-lexicon-input]").forEach(function (input) {
      input.addEventListener("input", function () { updatePreview(input); });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
