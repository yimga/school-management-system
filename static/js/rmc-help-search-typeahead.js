/**
 * Help center KB search typeahead (batch 1339).
 */
(function () {
  "use strict";

  function typeaheadUrl() {
    var el = document.querySelector("[data-kb-typeahead-url]");
    return el ? el.getAttribute("data-kb-typeahead-url") : "";
  }

  function listEl() {
    return document.getElementById("rmc-help-typeahead");
  }

  function bindInput(input) {
    var url = typeaheadUrl();
    var list = listEl();
    if (!url || !input) return;
    var debounce;
    input.addEventListener("input", function () {
      clearTimeout(debounce);
      var q = (input.value || "").trim();
      if (q.length < 2) {
        if (list) list.classList.add("d-none");
        return;
      }
      debounce = setTimeout(function () {
        fetch(url + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            if (!list) return;
            list.innerHTML = "";
            var items = data.suggestions || [];
            if (!items.length) {
              list.classList.add("d-none");
              return;
            }
            items.forEach(function (row) {
              var a = document.createElement("a");
              a.className = "list-group-item list-group-item-action py-2 small";
              a.href = row.url || "#";
              a.textContent = row.title || "";
              list.appendChild(a);
            });
            list.classList.remove("d-none");
          })
          .catch(function () {
            if (list) list.classList.add("d-none");
          });
      }, 280);
    });
  }

  function init() {
    document.querySelectorAll("[data-rmc-help-search-input]").forEach(bindInput);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
