/**
 * Marketing sovereign KB typeahead (batch 1357).
 */
(function () {
  "use strict";

  function typeaheadUrl() {
    var el = document.querySelector("[data-mkt-kb-typeahead-url]");
    return el ? el.getAttribute("data-mkt-kb-typeahead-url") : "";
  }

  function mount(input) {
    var base = typeaheadUrl();
    if (!base || !input) return;
    var panel = document.createElement("div");
    panel.className = "list-group position-absolute w-100 shadow-sm";
    panel.setAttribute("role", "listbox");
    panel.hidden = true;
    panel.style.zIndex = "20";
    input.parentElement.style.position = "relative";
    input.parentElement.appendChild(panel);

    var timer = null;
    input.addEventListener("input", function () {
      var q = (input.value || "").trim();
      if (timer) clearTimeout(timer);
      if (q.length < 2) {
        panel.hidden = true;
        panel.innerHTML = "";
        return;
      }
      timer = setTimeout(function () {
        fetch(base + (base.indexOf("?") >= 0 ? "&" : "?") + "q=" + encodeURIComponent(q), {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            var items = (data && data.suggestions) || [];
            if (!items.length) {
              panel.hidden = true;
              panel.innerHTML = "";
              return;
            }
            panel.innerHTML = items
              .map(function (row) {
                var url = row.url || "#";
                var title = row.title || "";
                return (
                  '<a class="list-group-item list-group-item-action" role="option" href="' +
                  url +
                  '">' +
                  title +
                  "</a>"
                );
              })
              .join("");
            panel.hidden = false;
          })
          .catch(function () {
            panel.hidden = true;
          });
      }, 220);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-mkt-kb-typeahead]").forEach(mount);
  });
})();
