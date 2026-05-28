/**
 * Session-scoped wizard field cache (illustrative — no secrets).
 */
(function () {
  "use strict";

  function storageKey(root) {
    var id = root.getAttribute("data-rmc-wizard-cache-key") || "rmc-wizard";
    return "rmc:wizard:" + id;
  }

  function init(root) {
    if (root.getAttribute("data-rmc-wizard-cache") !== "session") return;
    var key = storageKey(root);
    root.querySelectorAll("[data-rmc-wizard-field]").forEach(function (el) {
      var field = el.getAttribute("data-rmc-wizard-field");
      if (!field) return;
      try {
        var raw = sessionStorage.getItem(key + ":" + field);
        if (raw && el.value === "") el.value = raw;
      } catch (e) {
        /* private mode */
      }
      el.addEventListener("input", function () {
        try {
          sessionStorage.setItem(key + ":" + field, el.value);
        } catch (err) {
          /* ignore */
        }
      });
    });
  }

  document.querySelectorAll("[data-rmc-wizard-viewport]").forEach(init);
})();
