/**
 * Clinical pricing entitlement calculator (illustrative tiers).
 */
(function () {
  "use strict";

  var BASE = { transport: 4, grading: 6, comms: 3, billing: 8 };
  var SYMBOLS = { USD: "$", SAR: "﷼", BRL: "R$", NGN: "₦", INR: "₹", GBP: "£", EUR: "€" };

  function init(root) {
    var output = root.querySelector("[data-mkt-entitlement-output]");
    var currency = (root.getAttribute("data-currency") || "USD").toUpperCase();
    var sym = SYMBOLS[currency] || currency + " ";

    function recalc() {
      var total = 12;
      root.querySelectorAll("[data-mkt-module].is-active").forEach(function (btn) {
        var mod = btn.getAttribute("data-mkt-module");
        if (mod && BASE[mod]) total += BASE[mod];
      });
      if (output) {
        output.textContent =
          "Indicative tier · " + sym + " " + total + " / student / month (" + currency + ")";
      }
    }

    root.querySelectorAll("[data-mkt-module]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var on = btn.classList.toggle("is-active");
        btn.setAttribute("aria-pressed", on ? "true" : "false");
        recalc();
      });
    });
    recalc();
  }

  document.querySelectorAll("[data-mkt-entitlement-calculator]").forEach(init);
})();
