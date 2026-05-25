(function () {
  "use strict";
  document.querySelectorAll("[data-rmc-copy-mfa-secret]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var value = btn.getAttribute("data-rmc-copy-mfa-secret") || "";
      if (!value || !navigator.clipboard) return;
      navigator.clipboard.writeText(value).then(function () {
        btn.textContent = btn.getAttribute("data-rmc-copied-label") || "Copied";
      });
    });
  });
})();
