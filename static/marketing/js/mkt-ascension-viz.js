/**
 * Ascension media + data viz — orbit graph, count-up, cinematic parallax.
 */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── Orbit viz: student thread network ── */
  document.querySelectorAll("[data-mkt-orbit-viz]").forEach(function (el) {
    var c = document.createElement("canvas");
    c.setAttribute("aria-hidden", "true");
    el.appendChild(c);
    var ctx = c.getContext("2d");
    var nodes = [
      { x: 0.18, y: 0.55, label: "Admit", hue: 250 },
      { x: 0.38, y: 0.32, label: "Teach", hue: 270 },
      { x: 0.55, y: 0.62, label: "Pay", hue: 160 },
      { x: 0.72, y: 0.38, label: "Talk", hue: 200 },
      { x: 0.85, y: 0.58, label: "Grow", hue: 330 },
    ];
    var t = 0;
    function resize() {
      c.width = el.clientWidth;
      c.height = el.clientHeight;
    }
    function draw() {
      if (!reduced) t += 0.008;
      ctx.clearRect(0, 0, c.width, c.height);
      var w = c.width;
      var h = c.height;
      ctx.strokeStyle = "rgba(99,102,241,0.25)";
      ctx.lineWidth = 1.5;
      for (var i = 0; i < nodes.length - 1; i++) {
        ctx.beginPath();
        ctx.moveTo(nodes[i].x * w, nodes[i].y * h);
        ctx.lineTo(nodes[i + 1].x * w, nodes[i + 1].y * h);
        ctx.stroke();
      }
      nodes.forEach(function (n, idx) {
        var pulse = reduced ? 1 : 1 + Math.sin(t + idx) * 0.15;
        var r = 8 * pulse;
        ctx.beginPath();
        ctx.arc(n.x * w, n.y * h, r, 0, Math.PI * 2);
        ctx.fillStyle = "hsla(" + n.hue + ",70%,62%,0.85)";
        ctx.fill();
      });
      if (!reduced) requestAnimationFrame(draw);
    }
    resize();
    window.addEventListener("resize", resize);
    draw();
  });

  /* ── Count-up metrics ── */
  document.querySelectorAll("[data-mkt-count-up]").forEach(function (el) {
    var target = parseFloat(el.getAttribute("data-mkt-count-up") || "0");
    var suffix = el.getAttribute("data-mkt-count-suffix") || "";
    if (reduced || !("IntersectionObserver" in window)) {
      el.textContent = target + suffix;
      return;
    }
    var done = false;
    var io = new IntersectionObserver(function (entries) {
      if (done || !entries[0].isIntersecting) return;
      done = true;
      var start = performance.now();
      var dur = 1200;
      function tick(now) {
        var p = Math.min((now - start) / dur, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * eased) + suffix;
        if (p < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
      io.disconnect();
    }, { threshold: 0.4 });
    io.observe(el);
  });

  /* ── Cinematic film: play regional loop when in view ── */
  document.querySelectorAll(".mkt-asc-film video").forEach(function (vid) {
    vid.muted = true;
    vid.playsInline = true;
    if (reduced) return;
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) vid.play().catch(function () {});
          else vid.pause();
        });
      }, { threshold: 0.35 });
      io.observe(vid);
    }
  });

  /* ── Parallax media panels ── */
  if (!reduced) {
    document.querySelectorAll("[data-mkt-parallax]").forEach(function (panel) {
      window.addEventListener("scroll", function () {
        var rect = panel.getBoundingClientRect();
        var center = rect.top + rect.height * 0.5 - window.innerHeight * 0.5;
        var shift = Math.max(-24, Math.min(24, center * 0.04));
        panel.style.transform = "translate3d(0," + shift + "px,0)";
      }, { passive: true });
    });
  }
})();
