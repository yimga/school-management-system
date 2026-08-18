/**
 * Select-all for portal offline conflict bulk form.
 */
(function () {
  "use strict";

  function wire() {
    var master = document.querySelector("[data-rmc-offline-select-all]");
    if (!master) return;
    master.addEventListener("change", function () {
      var boxes = document.querySelectorAll('input[name="action_ids"][form="offline-conflict-bulk"]');
      for (var i = 0; i < boxes.length; i++) {
        boxes[i].checked = master.checked;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
