/**
 * 6-cell OTP input — syncs to a hidden/native field for form POST.
 */
(function () {
  function wireOtp(root) {
    var hidden = root.querySelector("[data-rmc-mfa-otp-value]");
    var cells = root.querySelectorAll(".rmc-mfa-otp__cell");
    if (!cells.length) return;

    function readValue() {
      var v = "";
      for (var i = 0; i < cells.length; i++) {
        v += (cells[i].value || "").replace(/\D/g, "").slice(0, 1);
      }
      return v;
    }

    function syncHidden() {
      var v = readValue();
      if (hidden) {
        hidden.value = v;
        hidden.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }

    function fillFromString(str) {
      var digits = String(str || "").replace(/\D/g, "").slice(0, cells.length);
      for (var i = 0; i < cells.length; i++) {
        cells[i].value = digits[i] || "";
      }
      syncHidden();
    }

    if (hidden && hidden.value) {
      fillFromString(hidden.value);
    }

    cells.forEach(function (cell, idx) {
      cell.addEventListener("input", function () {
        var d = cell.value.replace(/\D/g, "").slice(-1);
        cell.value = d;
        syncHidden();
        if (d && cells[idx + 1]) cells[idx + 1].focus();
      });
      cell.addEventListener("keydown", function (ev) {
        if (ev.key === "Backspace" && !cell.value && cells[idx - 1]) {
          cells[idx - 1].focus();
        }
        if (ev.key === "ArrowLeft" && cells[idx - 1]) {
          ev.preventDefault();
          cells[idx - 1].focus();
        }
        if (ev.key === "ArrowRight" && cells[idx + 1]) {
          ev.preventDefault();
          cells[idx + 1].focus();
        }
      });
      cell.addEventListener("paste", function (ev) {
        ev.preventDefault();
        var text = (ev.clipboardData || window.clipboardData).getData("text") || "";
        fillFromString(text);
        var len = readValue().length;
        if (cells[len]) cells[len].focus();
        else if (cells[cells.length - 1]) cells[cells.length - 1].focus();
      });
    });
  }

  document.querySelectorAll("[data-rmc-mfa-otp]").forEach(wireOtp);
})();
