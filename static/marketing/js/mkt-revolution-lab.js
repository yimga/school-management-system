/**
 * Revolution lab — gate enter, competitor arena split, monolith → live sim anchors.
 */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var enter = document.querySelector("[data-mkt-rev-enter]");
  if (enter) {
    enter.addEventListener("click", function () {
      var target =
        document.getElementById("mkt-hero-speed-duel") ||
        document.querySelector(".mkt-rev-proof-banner");
      if (target) {
        target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }
    });
  }

  var arenaData = {
    ps: {
      them: "Months to deploy. Relational schema — custom fields are dev tickets. Internet-only posture.",
      us: "Runtime manifests. Migration wizard. Offline queue with reconciliation — run the sims below.",
    },
    toddle: {
      them: "Best-in-class IB classroom — stops at the classroom wall.",
      us: "IB morph + fees + parent window on one student thread.",
    },
    arbor: {
      them: "UK register excellence — legacy UX, single-curriculum bias.",
      us: "Polymorphic grading + GDPR posture. RTL-native layout.",
    },
    bright: {
      them: "Early-years delight — schools outgrow when secondary ops arrive.",
      us: "K-12 through network scale — same calm parent surface.",
    },
  };

  var arena = document.querySelector("[data-mkt-revolution-arena]");
  if (arena) {
    var stage = arena.querySelector(".mkt-rev-arena__stage");
    var handle = arena.querySelector(".mkt-rev-arena__handle");
    var slider = arena.querySelector(".mkt-rev-arena__slider");
    var themHalf = arena.querySelector(".mkt-rev-arena__half--them");
    var usHalf = arena.querySelector(".mkt-rev-arena__half--us");
    var themText = arena.querySelector("[data-rev-them-text]");
    var usText = arena.querySelector("[data-rev-us-text]");
    var activeKey = "ps";
    var splitPct = 50;
    var dragging = false;

    function applySplit(pct) {
      splitPct = Math.max(12, Math.min(88, pct));
      if (themHalf) themHalf.style.clipPath = "inset(0 " + (100 - splitPct) + "% 0 0)";
      if (usHalf) usHalf.style.clipPath = "inset(0 0 0 " + splitPct + "%)";
      if (handle) handle.style.left = splitPct + "%";
      if (slider) slider.value = String(Math.round(splitPct));
    }

    function applyCompetitor(key) {
      activeKey = key;
      var row = arenaData[key] || arenaData.ps;
      if (themText) themText.innerHTML = "<strong>Their reality.</strong> " + row.them;
      if (usText) usText.innerHTML = "<strong>RunMyCampus.</strong> " + row.us;
      arena.querySelectorAll(".mkt-rev-arena__pick").forEach(function (btn) {
        btn.classList.toggle("is-active", btn.getAttribute("data-rev-vs") === key);
      });
    }

    arena.querySelectorAll(".mkt-rev-arena__pick").forEach(function (btn) {
      btn.addEventListener("click", function () {
        applyCompetitor(btn.getAttribute("data-rev-vs"));
      });
    });

    if (slider) {
      slider.addEventListener("input", function () {
        applySplit(Number(slider.value));
      });
    }

    if (stage && handle) {
      function pointerX(ev) {
        var rect = stage.getBoundingClientRect();
        return ((ev.clientX - rect.left) / rect.width) * 100;
      }
      handle.addEventListener("pointerdown", function (ev) {
        dragging = true;
        handle.setPointerCapture(ev.pointerId);
      });
      handle.addEventListener("pointermove", function (ev) {
        if (!dragging) return;
        applySplit(pointerX(ev));
      });
      handle.addEventListener("pointerup", function () {
        dragging = false;
      });
    }

    applyCompetitor("ps");
    applySplit(50);
  }

  var monolithTargets = {
    run: ["mkt-hero-speed-duel", "ch-run", "mkt-sovereign-kernel"],
    teach: ["ch-teach", "mkt-fluid-classroom"],
    pay: ["ch-pay", "mkt-clinical-ledger"],
    talk: ["ch-talk"],
    govern: ["ch-govern", "mkt-rugged-engine"],
    grow: ["ch-grow", "mkt-simulations-hub"],
  };

  function scrollToVerb(v) {
    var ids = monolithTargets[v] || [];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el) {
        el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
        return;
      }
    }
  }

  document.querySelectorAll(".mkt-asc-monolith").forEach(function (btn) {
    btn.addEventListener("click", function () {
      scrollToVerb(btn.getAttribute("data-v"));
    });
  });
})();
