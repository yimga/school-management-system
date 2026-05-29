/**
 * Illustrative global edge map — city hover shows RTT, currency, PPP.
 */
(function () {
  "use strict";

  function init(root) {
    var cities = root.querySelectorAll("[data-mkt-edge-city]");
    var rtt = root.querySelector("[data-mkt-edge-rtt]");
    var currency = root.querySelector("[data-mkt-edge-currency]");
    var ppp = root.querySelector("[data-mkt-edge-ppp]");

    function apply(btn) {
      cities.forEach(function (c) {
        c.classList.remove("is-active");
        c.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("is-active");
      btn.setAttribute("aria-pressed", "true");
      if (rtt) rtt.textContent = (btn.getAttribute("data-edge-ms") || "—") + " ms";
      if (currency) currency.textContent = btn.getAttribute("data-currency") || "—";
      if (ppp) ppp.textContent = btn.getAttribute("data-ppp") || "—";
    }

    cities.forEach(function (btn) {
      btn.addEventListener("click", function () {
        apply(btn);
      });
    });

    var active = root.querySelector("[data-mkt-edge-city].is-active");
    if (active) apply(active);
  }

  document.querySelectorAll("[data-mkt-edge-map]").forEach(init);
})();
