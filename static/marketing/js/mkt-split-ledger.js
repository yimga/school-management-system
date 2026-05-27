/**
 * Clinical ledger split slider — updates illustrative SVG bar widths.
 */
(function () {
  "use strict";
  function init(root) {
    var slider = root.querySelector("[data-mkt-split-slider]");
    var svg = root.querySelector(".mkt-viz--split-ledger");
    if (!slider || !svg) return;
    var tuition = svg.querySelector("rect:nth-of-type(3)");
    var activity = svg.querySelector("rect:nth-of-type(4)");
    if (!tuition || !activity) return;
    function apply() {
      var pct = Number(slider.value) / 100;
      var totalW = 352;
      var tW = Math.round(totalW * pct);
      var aW = totalW - tW;
      tuition.setAttribute("width", String(tW));
      activity.setAttribute("x", String(24 + tW + 12));
      activity.setAttribute("width", String(aW));
      slider.setAttribute("aria-valuenow", slider.value);
    }
    slider.addEventListener("input", apply);
    apply();
  }
  document.querySelectorAll("[data-mkt-split-ledger]").forEach(init);
})();
