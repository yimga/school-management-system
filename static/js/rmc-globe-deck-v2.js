/**
 * WOW v2 globe deck — crown proxies, freshness mirror, rail → globe wiring.
 */
(function () {
  var deck = document.querySelector("[data-rmc-cp-globe-deck-v2='1']");
  if (!deck) return;

  deck.querySelectorAll("[data-rmc-globe-deck-proxy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.getAttribute("data-rmc-globe-deck-proxy");
      if (!id) return;
      var target = document.getElementById(id);
      if (target && typeof target.click === "function") target.click();
    });
  });

  var freshnessSrc = document.getElementById("rmc-world-globe-freshness");
  var freshnessDst = document.getElementById("rmc-globe-deck-v2-freshness");
  if (freshnessSrc && freshnessDst) {
    function mirrorFreshness() {
      var t = (freshnessSrc.textContent || "").trim();
      if (t) freshnessDst.textContent = t;
    }
    mirrorFreshness();
    if (typeof MutationObserver !== "undefined") {
      var obs = new MutationObserver(mirrorFreshness);
      obs.observe(freshnessSrc, { childList: true, characterData: true, subtree: true });
    }
  }

  var heroN = document.getElementById("rmc-world-globe-hero-n");
  var deckN = document.getElementById("rmc-globe-deck-v2-schools-n");
  if (heroN && deckN) {
    function mirrorSchools() {
      var v = (heroN.textContent || "").trim();
      if (v) deckN.textContent = v;
    }
    mirrorSchools();
    if (typeof MutationObserver !== "undefined") {
      var obs2 = new MutationObserver(mirrorSchools);
      obs2.observe(heroN, { childList: true, characterData: true, subtree: true });
    }
  }

  var lab = document.getElementById("rmc-globe-master-lab");
  if (!lab) return;

  deck.querySelectorAll(".rmc-globe-deck-v2__region-row").forEach(function (row) {
    row.addEventListener("click", function () {
      var region = row.getAttribute("data-rmc-region");
      if (!region) return;
      var target =
        lab.querySelector('[data-rmc-region="' + region + '"].lx-world__legend-row') ||
        lab.querySelector('[data-rmc-region="' + region + '"].lx-world__orbit-chip') ||
        lab.querySelector('[data-rmc-region="' + region + '"].lx-world__glass-dock-chip');
      if (target && typeof target.click === "function") target.click();
    });
  });

  deck.querySelectorAll(".rmc-globe-deck-v2__status-chip").forEach(function (chip) {
    chip.setAttribute("role", "button");
    chip.setAttribute("tabindex", "0");
    chip.addEventListener("click", function () {
      var status = chip.getAttribute("data-rmc-status-filter");
      if (!status) return;
      var legendChip = lab.querySelector(
        '.lx-world__status-chip[data-rmc-status-filter="' + status + '"]'
      );
      if (legendChip && typeof legendChip.click === "function") legendChip.click();
      deck.querySelectorAll(".rmc-globe-deck-v2__status-chip").forEach(function (c) {
        c.classList.toggle("on", c === chip);
      });
    });
  });
})();
