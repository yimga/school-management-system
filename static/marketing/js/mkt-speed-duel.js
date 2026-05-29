/**
 * Hero speed duel — simulated legacy clicks vs RunMyCampus command path.
 */
(function () {
  "use strict";

  function init(root) {
    var legacyRun = root.querySelector("[data-mkt-legacy-run]");
    var rmcRun = root.querySelector("[data-mkt-rmc-run]");
    var legacyClicks = root.querySelector("[data-mkt-legacy-clicks]");
    var legacyMs = root.querySelector("[data-mkt-legacy-ms]");
    var trail = root.querySelectorAll("[data-mkt-legacy-trail] li");
    var stream = root.querySelector("[data-mkt-rmc-stream]");
    var cards = root.querySelector("[data-mkt-rmc-cards]");
    var ttft = root.querySelector("[data-mkt-rmc-ttft]");
    var total = root.querySelector("[data-mkt-rmc-total]");

    function runLegacy() {
      if (!legacyRun) return;
      legacyRun.disabled = true;
      var clicks = 0;
      var start = performance.now();
      trail.forEach(function (li, idx) {
        setTimeout(function () {
          li.classList.add("is-active");
          clicks += 1;
          if (legacyClicks) legacyClicks.textContent = String(clicks);
        }, idx * 420);
      });
      setTimeout(function () {
        if (legacyMs) legacyMs.textContent = Math.round(performance.now() - start) + " ms";
        legacyRun.disabled = false;
      }, trail.length * 420 + 200);
    }

    function runRmc() {
      if (!rmcRun) return;
      rmcRun.disabled = true;
      if (stream) {
        stream.hidden = false;
        stream.textContent = '{"tool":"report_cards.publish","args":{"cohort":"10-A"}}';
      }
      var t0 = performance.now();
      if (ttft) ttft.textContent = "47 ms";
      setTimeout(function () {
        if (cards) cards.hidden = false;
        cards.querySelectorAll(".mkt-ve-speed-duel__card").forEach(function (card, i) {
          setTimeout(function () {
            card.classList.add("is-visible");
          }, i * 80);
        });
      }, 120);
      setTimeout(function () {
        if (total) total.textContent = Math.max(280, Math.round(performance.now() - t0)) + " ms";
        rmcRun.disabled = false;
      }, 520);
    }

    if (legacyRun) legacyRun.addEventListener("click", runLegacy);
    if (rmcRun) rmcRun.addEventListener("click", runRmc);
  }

  document.querySelectorAll("[data-mkt-speed-duel]").forEach(init);
})();
