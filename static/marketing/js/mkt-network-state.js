/**
 * Rugged engine online/offline toggle (illustrative sync queue).
 */
(function () {
  "use strict";

  var ONLINE_LABEL = "Simulated queue · 3 devices synced";
  var OFFLINE_LABEL = "Simulated · 3 events queued for sync";

  function init(root) {
    var status = root.querySelector("[data-mkt-network-status]");
    var buttons = root.querySelectorAll("[data-mkt-network]");
    var queueLabel = root.querySelector("[data-mkt-queue-label]");

    function applyState(offline) {
      root.classList.toggle("is-offline", offline);
      if (status) {
        status.textContent = offline
          ? status.getAttribute("data-offline-label") || OFFLINE_LABEL
          : status.getAttribute("data-online-label") || ONLINE_LABEL;
      }
      if (queueLabel) {
        queueLabel.textContent = offline
          ? status && status.getAttribute("data-offline-label")
            ? status.getAttribute("data-offline-label")
            : OFFLINE_LABEL
          : status && status.getAttribute("data-online-label")
            ? status.getAttribute("data-online-label")
            : ONLINE_LABEL;
      }
    }

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) {
          b.classList.remove("is-active");
          b.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("is-active");
        btn.setAttribute("aria-pressed", "true");
        applyState(btn.getAttribute("data-mkt-network") === "offline");
      });
    });
  }

  document.querySelectorAll("[data-mkt-network-state]").forEach(init);
})();
