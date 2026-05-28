/* v4.00.12 — Platform-wide list-page bulk actions wiring.

   Pages opt in by:
   1. Adding `data-rmc-bulk-table` to a <table>.
   2. Including `templates/components/_bulk_actions_toolbar.html` with
      `data-rmc-bulk-toolbar-for="<table-id>"`.
   3. Adding `<input type="checkbox" data-rmc-bulk-checkbox value="<row-id>">`
      to the first cell of every row.
   4. Optional: a header checkbox with `data-rmc-bulk-select-all`.

   Each toolbar action button carries `data-rmc-bulk-action="<slug>"`. When a
   user clicks it, the script fires a `rmc:bulk-action` CustomEvent with
   `{action, ids}` on the table — pages listen and POST to their own endpoint
   (no global endpoint convention to avoid CSRF rope-pulling).
*/

(function () {
  "use strict";

  function selectedIds(table) {
    var boxes = table.querySelectorAll("input[data-rmc-bulk-checkbox]:checked");
    var ids = [];
    for (var i = 0; i < boxes.length; i++) {
      ids.push(boxes[i].value);
    }
    return ids;
  }

  function updateToolbar(table) {
    var tableId = table.id || "";
    if (!tableId) {
      return;
    }
    var toolbar = document.querySelector('[data-rmc-bulk-toolbar-for="' + tableId + '"]');
    if (!toolbar) {
      return;
    }
    var ids = selectedIds(table);
    var countEl = toolbar.querySelector("[data-rmc-bulk-count]");
    if (countEl) {
      countEl.textContent = String(ids.length);
    }
    if (ids.length > 0) {
      toolbar.setAttribute("data-rmc-bulk-active", "1");
    } else {
      toolbar.removeAttribute("data-rmc-bulk-active");
    }
    // Mark row state for styling
    var rows = table.querySelectorAll("tbody tr");
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var cb = row.querySelector("input[data-rmc-bulk-checkbox]");
      if (cb && cb.checked) {
        row.setAttribute("data-rmc-bulk-selected", "1");
      } else {
        row.removeAttribute("data-rmc-bulk-selected");
      }
    }
  }

  function wireTable(table) {
    if (table.getAttribute("data-rmc-bulk-wired") === "1") {
      return;
    }
    table.setAttribute("data-rmc-bulk-wired", "1");

    table.addEventListener("change", function (ev) {
      var t = ev.target;
      if (!t) { return; }
      if (t.matches("input[data-rmc-bulk-select-all]")) {
        var boxes = table.querySelectorAll("input[data-rmc-bulk-checkbox]");
        for (var i = 0; i < boxes.length; i++) {
          boxes[i].checked = t.checked;
        }
        updateToolbar(table);
      } else if (t.matches("input[data-rmc-bulk-checkbox]")) {
        updateToolbar(table);
      }
    });

    var tableId = table.id || "";
    if (tableId) {
      var toolbar = document.querySelector('[data-rmc-bulk-toolbar-for="' + tableId + '"]');
      if (toolbar) {
        toolbar.addEventListener("click", function (ev) {
          var btn = ev.target.closest("[data-rmc-bulk-action]");
          if (btn) {
            ev.preventDefault();
            var action = btn.getAttribute("data-rmc-bulk-action");
            var ids = selectedIds(table);
            if (ids.length === 0) { return; }
            table.dispatchEvent(new CustomEvent("rmc:bulk-action", {
              detail: { action: action, ids: ids },
              bubbles: true,
            }));
          } else if (ev.target.closest("[data-rmc-bulk-clear]")) {
            ev.preventDefault();
            var boxes = table.querySelectorAll("input[data-rmc-bulk-checkbox], input[data-rmc-bulk-select-all]");
            for (var i = 0; i < boxes.length; i++) { boxes[i].checked = false; }
            updateToolbar(table);
          }
        });
      }
    }
    updateToolbar(table);
  }

  function bootstrap() {
    var tables = document.querySelectorAll("table[data-rmc-bulk-table]");
    for (var i = 0; i < tables.length; i++) {
      wireTable(tables[i]);
    }
  }

  // v4.00.13: CSRF helper for consumers — reads token from <meta name="csrf-token">
  // or the standard Django cookie, then POSTs JSON with X-CSRFToken header.
  function readCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.getAttribute("content")) {
      return meta.getAttribute("content");
    }
    var cookies = (document.cookie || "").split(";");
    for (var i = 0; i < cookies.length; i++) {
      var raw = cookies[i].trim();
      if (raw.indexOf("csrftoken=") === 0) {
        return decodeURIComponent(raw.substring("csrftoken=".length));
      }
    }
    return "";
  }

  function postWithCsrf(url, payload) {
    var token = readCsrfToken();
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-CSRFToken": token,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload || {}),
    });
  }

  window.rmcBulkActions = window.rmcBulkActions || {};
  window.rmcBulkActions.postWithCsrf = postWithCsrf;
  window.rmcBulkActions.readCsrfToken = readCsrfToken;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }
})();
