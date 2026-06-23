/**
 * Ascension marketing lab — canvas, day narrative, competitor wall, mini sims.
 */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── Aurora canvas ── */
  var wrap = document.getElementById("asc-canvas-wrap");
  if (wrap && !reduced) {
    var c = document.createElement("canvas");
    wrap.appendChild(c);
    var ctx = c.getContext("2d");
    var pts = [];
    var i;
    function resize() {
      c.width = wrap.clientWidth;
      c.height = wrap.clientHeight;
    }
    for (i = 0; i < 48; i++) {
      pts.push({
        x: Math.random(),
        y: Math.random(),
        r: 0.002 + Math.random() * 0.004,
        vx: (Math.random() - 0.5) * 0.0004,
        vy: (Math.random() - 0.5) * 0.0004,
        hue: 220 + Math.random() * 80,
      });
    }
    function draw() {
      ctx.clearRect(0, 0, c.width, c.height);
      var g = ctx.createRadialGradient(
        c.width * 0.5, c.height * 0.35, 0,
        c.width * 0.5, c.height * 0.35, c.width * 0.55
      );
      g.addColorStop(0, "rgba(99,102,241,0.12)");
      g.addColorStop(1, "transparent");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, c.width, c.height);
      pts.forEach(function (p) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > 1) p.vx *= -1;
        if (p.y < 0 || p.y > 1) p.vy *= -1;
        ctx.beginPath();
        ctx.arc(p.x * c.width, p.y * c.height, p.r * c.width, 0, Math.PI * 2);
        ctx.fillStyle = "hsla(" + p.hue + ",70%,65%,0.35)";
        ctx.fill();
      });
      requestAnimationFrame(draw);
    }
    resize();
    window.addEventListener("resize", resize);
    draw();
  }

  /* ── Monolith doors → scroll to chapter ── */
  var targetIds = {
    run: ["mkt-hero-speed-duel", "ch-run", "mkt-sovereign-kernel"],
    teach: ["ch-teach", "mkt-fluid-classroom"],
    pay: ["ch-pay", "mkt-clinical-ledger"],
    talk: ["ch-talk", "mkt-sovereign-kernel"],
    govern: ["ch-govern", "mkt-rugged-engine"],
    grow: ["ch-grow", "asc-finale", "mkt-simulations-hub"],
  };
  function resolveTarget(v) {
    var ids = targetIds[v] || [];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el) return el;
    }
    return null;
  }
  document.querySelectorAll(".mkt-asc-monolith").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".mkt-asc-monolith").forEach(function (b) { b.classList.remove("is-active"); });
      btn.classList.add("is-active");
      var el = resolveTarget(btn.getAttribute("data-v"));
      if (el) el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    });
  });

  /* ── Day chips sync with scroll ── */
  var chips = document.querySelectorAll(".mkt-asc-day__chip");
  var chapters = document.querySelectorAll(".mkt-asc-chapter");
  if (chips.length && chapters.length && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          var id = e.target.id;
          chips.forEach(function (chip) {
            chip.classList.toggle("is-active", chip.getAttribute("data-ch") === id);
          });
        });
      },
      { threshold: 0.45, rootMargin: "-20% 0px -35% 0px" }
    );
    chapters.forEach(function (ch) { io.observe(ch); });
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        var t = document.getElementById(chip.getAttribute("data-ch"));
        if (t) t.scrollIntoView({ behavior: reduced ? "auto" : "smooth" });
      });
    });
  }

  /* ── Competitor wall ── */
  document.querySelectorAll(".mkt-asc-vs__tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      var key = tab.getAttribute("data-vs");
      document.querySelectorAll(".mkt-asc-vs__tab").forEach(function (t) { t.classList.remove("is-active"); });
      document.querySelectorAll(".mkt-asc-vs__panel").forEach(function (p) { p.classList.remove("is-active"); });
      tab.classList.add("is-active");
      var panel = document.querySelector('.mkt-asc-vs__panel[data-vs="' + key + '"]');
      if (panel) panel.classList.add("is-active");
    });
  });

  /* ── Region morph (hero + sovereign sim) ── */
  var regions = {
    US: { cur: "USD", terms: "2 semesters", rtl: "LTR", hook: "CALPADS-ready migration path" },
    NG: { cur: "NGN", terms: "3 terms", rtl: "LTR", hook: "Pix-style APM + mobile money rails" },
    GB: { cur: "GBP", terms: "3 terms", rtl: "LTR", hook: "IB + A-Levels on one gradebook" },
    BR: { cur: "BRL", terms: "2 semesters", rtl: "LTR", hook: "NF-e / SEFAZ receipt stamps" },
    KE: { cur: "KES", terms: "3 terms", rtl: "LTR", hook: "M-Pesa split-wallet + offline queue" },
    AE: { cur: "AED", terms: "2 semesters", rtl: "RTL", hook: "RTL-native layout, no plugin" },
  };
  var regionSel = document.getElementById("asc-region");
  var regionOut = document.getElementById("asc-region-out");
  function applyRegion(code) {
    var r = regions[code] || regions.US;
    if (regionOut) {
      regionOut.innerHTML =
        "<strong>" + code + "</strong> · " + r.cur + " · " + r.terms + " · " + r.rtl +
        "<br><span style='opacity:0.75;font-size:0.875rem'>" + r.hook + "</span>";
    }
    document.documentElement.style.setProperty("--asc-accent", code === "AE" ? "#d97706" : "#c2410c");
  }
  if (regionSel) {
    regionSel.addEventListener("change", function () { applyRegion(regionSel.value); });
    var boot =
      (regionSel.value || "").trim().toUpperCase() ||
      (document.body.getAttribute("data-rmc-country") || "US").trim().toUpperCase();
    if (!regions[boot]) boot = "US";
    regionSel.value = boot;
    applyRegion(boot);
  } else if (regionOut) {
    var code = (document.body.getAttribute("data-rmc-country") || "US").trim().toUpperCase();
    applyRegion(regions[code] ? code : "US");
  }

  /* ── Split ledger mini sim ── */
  var splitBtn = document.getElementById("asc-split-run");
  if (splitBtn) {
    splitBtn.addEventListener("click", function () {
      var bars = document.querySelectorAll(".mkt-asc-split-bar");
      bars.forEach(function (b, idx) {
        b.style.width = "0%";
        setTimeout(function () {
          b.style.width = b.getAttribute("data-w") + "%";
        }, 80 + idx * 120);
      });
    });
    splitBtn.click();
  }

  /* ── Network drop sim ── */
  var netBtn = document.getElementById("asc-net-toggle");
  var netLabel = document.getElementById("asc-net-label");
  if (netBtn) {
    var online = true;
    netBtn.addEventListener("click", function () {
      online = !online;
      netLabel.textContent = online ? "Fiber · sync queue idle" : "Blackout · USSD + local queue active";
      netBtn.classList.toggle("is-offline", !online);
    });
  }

  /* ── Gradebook morph ── */
  document.querySelectorAll("[data-grade-scale]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var scale = btn.getAttribute("data-grade-scale");
      var out = document.getElementById("asc-grade-out");
      var labels = {
        US: "A- · 92% · Honor roll",
        IB: "6 · IB MYP · Approaching",
        CM: "A · 78% · Competency: Proficient",
      };
      document.querySelectorAll("[data-grade-scale]").forEach(function (b) { b.classList.remove("is-active"); });
      btn.classList.add("is-active");
      if (out) out.textContent = labels[scale] || labels.US;
    });
  });

  /* ── Progress + chrome ── */
  var prog = document.getElementById("asc-progress");
  if (prog) {
    window.addEventListener("scroll", function () {
      var h = document.documentElement.scrollHeight - window.innerHeight;
      prog.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + "%";
    }, { passive: true });
  }

  var fsBtn = document.getElementById("asc-fullscreen");
  if (fsBtn) {
    fsBtn.addEventListener("click", function () {
      if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(function () {});
      else document.exitFullscreen();
    });
  }

  document.querySelectorAll(".mkt-asc-reveal").forEach(function (el) {
    el.classList.add("is-visible");
  });
})();
