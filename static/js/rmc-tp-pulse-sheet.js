/**
 * Tenant snapshot card drill-down (preview shell 100x phase 5).
 */
(function () {
  "use strict";

  function openFromCard(card) {
    var sheet = document.getElementById("rmcTpPulseDrillSheet");
    if (!sheet || typeof sheet.showModal !== "function") return;
    var head = card.querySelector(".tp-snap-card__head");
    var value = card.querySelector(".tp-snap-card__value");
    var label = card.querySelector(".tp-snap-card__label");
    var delta = card.querySelector(".tp-snap-card__delta");
    var title = document.getElementById("rmcTpPulseDrillTitle");
    var elHead = document.getElementById("rmcTpPulseDrillHead");
    var elValue = document.getElementById("rmcTpPulseDrillValue");
    var elLabel = document.getElementById("rmcTpPulseDrillLabel");
    var elDelta = document.getElementById("rmcTpPulseDrillDelta");
    if (title) title.textContent = head ? head.textContent.trim() : "Metric";
    if (elHead) elHead.textContent = head ? head.textContent.trim() : "";
    if (elValue) elValue.textContent = value ? value.textContent.trim() : "—";
    if (elLabel) elLabel.textContent = label ? label.textContent.trim() : "";
    if (elDelta) elDelta.textContent = delta ? delta.textContent.trim() : "";
    sheet.showModal();
  }

  document.addEventListener("click", function (e) {
    var card = e.target && e.target.closest ? e.target.closest("[data-rmc-tp-pulse-drill]") : null;
    if (!card) return;
    e.preventDefault();
    openFromCard(card);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var card = e.target && e.target.closest ? e.target.closest("[data-rmc-tp-pulse-drill]") : null;
    if (!card) return;
    e.preventDefault();
    openFromCard(card);
  });
})();
