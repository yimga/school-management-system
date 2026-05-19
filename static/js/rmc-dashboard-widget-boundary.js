/**
 * Per-widget error isolation for server-rendered dashboard panels.
 * Marks failed fetch targets and exposes Retry without reloading the shell.
 */
(function () {
  "use strict";

  function armBoundary(root) {
    if (!root || root.dataset.rmcWidgetBoundaryArmed === "1") {
      return;
    }
    root.dataset.rmcWidgetBoundaryArmed = "1";
    var body = root.querySelector("[data-widget-body]");
    var err = root.querySelector("[data-widget-error]");
    var retry = root.querySelector("[data-widget-retry]");
    if (!body || !err || !retry) {
      return;
    }
    retry.addEventListener("click", function () {
      err.classList.add("d-none");
      body.classList.remove("d-none");
      root.dispatchEvent(
        new CustomEvent("rmc-dashboard-widget-retry", { bubbles: true }),
      );
    });
    root.showWidgetError = function (message) {
      if (message) {
        var p = err.querySelector("p");
        if (p) {
          p.textContent = message;
        }
      }
      body.classList.add("d-none");
      err.classList.remove("d-none");
    };
  }

  function init() {
    document
      .querySelectorAll(".rmc-dashboard-widget-boundary")
      .forEach(armBoundary);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
