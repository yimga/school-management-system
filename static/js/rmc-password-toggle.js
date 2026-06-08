/**
 * Toggle password fields between masked (type=password) and visible (type=text).
 * Markup: wrapper [data-rmc-password-field] + button [data-rmc-password-toggle].
 */
(function () {
  "use strict";

  function wirePasswordField(wrap) {
    var input = wrap.querySelector("input");
    var btn = wrap.querySelector("[data-rmc-password-toggle]");
    if (!input || !btn || btn.dataset.rmcPasswordBound === "1") {
      return;
    }
    btn.dataset.rmcPasswordBound = "1";
    var icon = btn.querySelector("i");
    var showLabel = btn.getAttribute("data-label-show") || "Show password";
    var hideLabel = btn.getAttribute("data-label-hide") || "Hide password";

    btn.addEventListener("click", function () {
      var visible = input.type === "text";
      input.type = visible ? "password" : "text";
      btn.setAttribute("aria-pressed", visible ? "false" : "true");
      btn.setAttribute("aria-label", visible ? showLabel : hideLabel);
      if (icon) {
        icon.className = visible ? "bi bi-eye" : "bi bi-eye-slash";
      }
    });
  }

  function wire(root) {
    (root || document).querySelectorAll("[data-rmc-password-field]").forEach(wirePasswordField);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      wire(document);
    });
  } else {
    wire(document);
  }
})();
