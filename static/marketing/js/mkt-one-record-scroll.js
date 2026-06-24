/**
 * One Record Scroll — chapter ↔ sim panel sync (midpoint scroll spy + click rail).
 * Progressive enhancement: falls back to first panel when IO unavailable.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-mkt-one-record-scroll]");
  if (!root) return;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var chapters = Array.prototype.slice.call(root.querySelectorAll(".mkt-or__chapter"));
  var panels = {};
  Array.prototype.slice.call(root.querySelectorAll(".mkt-or__panel")).forEach(function (p) {
    panels[p.id] = p;
  });
  var stageLabel = root.querySelector("[data-mkt-or-stage-label]");
  var progress = document.querySelector("[data-mkt-or-progress]");
  var thread = root.querySelector("[data-mkt-or-thread]");
  var dots = [];
  var activeIndex = 0;
  var ticking = false;

  chapters.forEach(function (ch, i) {
    if (thread) {
      var dot = document.createElement("div");
      dot.className = "mkt-or__thread-dot" + (i === 0 ? " is-active" : "");
      dot.style.top = (i * (100 / Math.max(chapters.length - 1, 1))) + "%";
      thread.appendChild(dot);
      dots.push(dot);
    }
    ch.addEventListener("click", function () {
      ch.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
      setActive(i, { force: true });
    });
  });

  function setActive(index, opts) {
    opts = opts || {};
    if (index < 0 || index >= chapters.length) return;
    if (!opts.force && index === activeIndex) return;
    activeIndex = index;
    chapters.forEach(function (ch, i) {
      ch.classList.toggle("is-active", i === index);
      ch.setAttribute("aria-current", i === index ? "true" : "false");
    });
    dots.forEach(function (d, i) {
      d.classList.toggle("is-active", i === index);
    });
    var ch = chapters[index];
    if (!ch) return;
    var panelId = ch.getAttribute("data-mkt-or-panel");
    Object.keys(panels).forEach(function (id) {
      panels[id].classList.toggle("is-active", id === panelId);
      panels[id].hidden = id !== panelId;
    });
    if (stageLabel && panels[panelId]) {
      stageLabel.textContent = panels[panelId].getAttribute("data-mkt-or-label") || "";
    }
    root.dispatchEvent(
      new CustomEvent("mkt-or-panel-active", {
        bubbles: true,
        detail: { panelId: panelId, index: index },
      })
    );
  }

  function pickByMidpoint() {
    var center = window.innerHeight * 0.42;
    var best = 0;
    var bestDist = Infinity;
    chapters.forEach(function (ch, i) {
      var rect = ch.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) return;
      var mid = rect.top + rect.height * 0.5;
      var dist = Math.abs(mid - center);
      if (dist < bestDist) {
        bestDist = dist;
        best = i;
      }
    });
    setActive(best);
  }

  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      ticking = false;
      if (progress) {
        var doc = document.documentElement;
        var pct =
          doc.scrollHeight <= doc.clientHeight
            ? 0
            : (window.scrollY / (doc.scrollHeight - doc.clientHeight)) * 100;
        progress.style.width = pct + "%";
      }
      pickByMidpoint();
    });
  }

  if ("IntersectionObserver" in window && chapters.length) {
    var io = new IntersectionObserver(
      function (entries) {
        var visible = entries
          .filter(function (e) {
            return e.isIntersecting;
          })
          .sort(function (a, b) {
            return b.intersectionRatio - a.intersectionRatio;
          });
        if (visible.length) {
          var idx = chapters.indexOf(visible[0].target);
          if (idx >= 0) setActive(idx);
        }
      },
      { root: null, rootMargin: "-35% 0px -35% 0px", threshold: [0, 0.25, 0.5] }
    );
    chapters.forEach(function (ch) {
      io.observe(ch);
    });
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", pickByMidpoint, { passive: true });
  setActive(0);
  onScroll();
})();
