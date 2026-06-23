/**
 * Revolution lab — gate enter, competitor arena split, monolith → live sim anchors.
 */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var enter = document.querySelector("[data-mkt-rev-enter]");
  var portal = document.querySelector("[data-mkt-rev-portal]");
  var crossed = false;

  function crossThreshold(target) {
    if (crossed) {
      if (target) {
        target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }
      return;
    }
    crossed = true;
    document.body.setAttribute("data-mkt-threshold-crossed", "1");
    if (portal && !reduced) {
      portal.classList.add("is-crossing");
      window.setTimeout(function () {
        portal.classList.remove("is-crossing");
        portal.classList.add("is-done");
      }, 1400);
    }
    window.setTimeout(function () {
      if (target) {
        target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }
    }, reduced ? 0 : 720);
  }

  if (enter) {
    enter.addEventListener("click", function () {
      var target =
        document.getElementById("mkt-hero-speed-duel") ||
        document.querySelector(".mkt-rev-proof-strip");
      crossThreshold(target);
    });
  }

  var arenaData = {
    ps: {
      them: "Enterprise SIS scale — but months to deploy, custom fields as dev tickets, and internet-only when the link drops.",
      us: "One command vs fifteen clicks (Speed Duel below). Region-aware sovereign wizard. Offline queue that reconciles when fiber returns.",
      wins: [
        { label: "Where we win", text: "Sub-100ms intent path vs nested menu hunting — simulated live on this page." },
        { label: "Where we win", text: "Migration Cloud + runtime manifests vs relational re-implementations." },
        { label: "Where we win", text: "Offline-first attendance + split ledger across 10+ tax authorities — not US-only." },
      ],
    },
    toddle: {
      them: "Best-in-class IB/PYP classroom UX — portfolios, unit planners, and teacher delight inside the classroom wall.",
      us: "Same polymorphic gradebook morph — plus fees, parent window, and admissions on one student thread.",
      wins: [
        { label: "Where we win", text: "IB 1–7 morph sim — same record, zero re-entry (Fluid Classroom below)." },
        { label: "Where we win", text: "Finance + comms + academics share one tenant — Toddle stops at the classroom." },
        { label: "Where we win", text: "180 currencies + RTL-native layout for international campuses they don't optimize for." },
      ],
    },
    arbor: {
      them: "UK register excellence, MAT dashboards, and compliance familiarity — legacy UX and UK-curriculum bias.",
      us: "Polymorphic grading across US, IB, Cambridge, and competency — GDPR posture + Africa/MENA payment rails built in.",
      wins: [
        { label: "Where we win", text: "Multi-framework gradebook without ripping out history — not single-curriculum lock-in." },
        { label: "Where we win", text: "M-Pesa / Pix / SPEI split-ledger sim — regions Arbor treats as afterthoughts." },
        { label: "Where we win", text: "Public trust center + procurement packet in footer — buyer-ready evidence, not PDF scavenger hunts." },
      ],
    },
    bright: {
      them: "Early-years parent delight — billing, daily sheets, and beautiful mobile comms for childcare.",
      us: "Same calm parent surface — scaled through secondary ops, multi-campus groups, and network analytics.",
      wins: [
        { label: "Where we win", text: "K-12 through diocese / PE group scale without swapping systems at Grade 6." },
        { label: "Where we win", text: "Clinical ledger + entitlement calculator — secondary fees, transport, and lunch splits." },
        { label: "Where we win", text: "Developer APIs + marketplace in footer — builders extend the OS, not bolt on shadow IT." },
      ],
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
    var winsRoot = arena.querySelector("[data-rev-wins]");
    var splitPct = 50;
    var dragging = false;

    function applySplit(pct) {
      splitPct = Math.max(12, Math.min(88, pct));
      if (themHalf) themHalf.style.clipPath = "inset(0 " + (100 - splitPct) + "% 0 0)";
      if (usHalf) usHalf.style.clipPath = "inset(0 0 0 " + splitPct + "%)";
      if (handle) handle.style.left = splitPct + "%";
      if (slider) slider.value = String(Math.round(splitPct));
    }

    function renderWins(wins) {
      if (!winsRoot) return;
      winsRoot.innerHTML = "";
      (wins || []).forEach(function (w) {
        var card = document.createElement("div");
        card.className = "mkt-rev-arena__win";
        card.innerHTML = "<strong>" + w.label + "</strong>" + w.text;
        winsRoot.appendChild(card);
      });
    }

    function applyCompetitor(key) {
      var row = arenaData[key] || arenaData.ps;
      if (themText) themText.innerHTML = "<strong>Their pitch.</strong> " + row.them;
      if (usText) usText.innerHTML = "<strong>RunMyCampus.</strong> " + row.us;
      renderWins(row.wins);
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
