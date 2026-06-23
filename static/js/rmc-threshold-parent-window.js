/**
 * Threshold Parent Window — rain canvas, window focus, optional ambient unlock.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-rmc-threshold-parent]");
  if (!root) return;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var windows = root.querySelectorAll("[data-rmc-tw-window]");
  var primaryDue = root.querySelector("[data-rmc-tw-primary-due]");

  windows.forEach(function (win) {
    win.addEventListener("click", function (e) {
      if (e.target.closest("a, button")) return;
      windows.forEach(function (w) {
        w.classList.remove("is-focused");
      });
      win.classList.add("is-focused");
    });
  });

  if (primaryDue) {
    var dueId = primaryDue.getAttribute("data-rmc-tw-primary-due");
    var dueWin = root.querySelector('[data-rmc-tw-window="' + dueId + '"]');
    if (dueWin) dueWin.classList.add("is-focused");
  }

  root.querySelectorAll("canvas[data-rmc-tw-rain]").forEach(function (canvas) {
    if (reduced) return;
    var ctx = canvas.getContext("2d");
    var drops = [];
    var i;
    for (i = 0; i < 36; i++) {
      drops.push({ x: Math.random(), y: Math.random(), v: 0.008 + Math.random() * 0.018 });
    }

    function resize() {
      var parent = canvas.parentElement;
      if (!parent) return;
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = "rgba(255,255,255,0.14)";
      ctx.lineWidth = 1;
      drops.forEach(function (d) {
        d.y += d.v;
        if (d.y > 1) {
          d.y = 0;
          d.x = Math.random();
        }
        ctx.beginPath();
        ctx.moveTo(d.x * canvas.width, d.y * canvas.height);
        ctx.lineTo(d.x * canvas.width - 2, d.y * canvas.height + 7);
        ctx.stroke();
      });
      requestAnimationFrame(draw);
    }

    resize();
    window.addEventListener("resize", resize);
    draw();
  });

  if (window.RmcThresholdAmbient) {
    root.addEventListener("click", function once() {
      var amb = window.__rmcThresholdAmbient;
      if (amb && amb.enabled) amb.unlock();
      root.removeEventListener("click", once);
    });
  }
})();
