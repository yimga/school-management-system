/**
 * Platform pulse card drill-down (preview shell 100x phase 5).
 * Opens rmc-bottom-sheet dialog with card metadata — no new routes.
 */
(function () {
  "use strict";

  function openFromCard(card) {
    var sheet = document.getElementById("rmcCpPulseDrillSheet");
    if (!sheet || typeof sheet.showModal !== "function") return;
    var head = card.querySelector(".rmc-cockpit-pulse-card__head");
    var value = card.querySelector(".rmc-cockpit-pulse-card__value");
    var label = card.querySelector(".rmc-cockpit-pulse-card__label");
    var delta = card.querySelector(".rmc-cockpit-pulse-card__delta");
    var title = document.getElementById("rmcCpPulseDrillTitle");
    var elHead = document.getElementById("rmcCpPulseDrillHead");
    var elValue = document.getElementById("rmcCpPulseDrillValue");
    var elLabel = document.getElementById("rmcCpPulseDrillLabel");
    var elDelta = document.getElementById("rmcCpPulseDrillDelta");
    if (title) title.textContent = head ? head.textContent.trim() : "Metric";
    if (elHead) elHead.textContent = head ? head.textContent.trim() : "";
    if (elValue) elValue.textContent = value ? value.textContent.trim() : "—";
    if (elLabel) elLabel.textContent = label ? label.textContent.trim() : "";
    if (elDelta) elDelta.textContent = delta ? delta.textContent.trim() : "";
    sheet.showModal();
  }

  document.addEventListener("click", function (e) {
    var card = e.target && e.target.closest ? e.target.closest("[data-rmc-cp-pulse-drill]") : null;
    if (!card) return;
    e.preventDefault();
    openFromCard(card);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var card = e.target && e.target.closest ? e.target.closest("[data-rmc-cp-pulse-drill]") : null;
    if (!card) return;
    e.preventDefault();
    openFromCard(card);
  });
})();
