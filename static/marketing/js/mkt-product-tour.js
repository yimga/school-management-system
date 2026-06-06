/*!
 * mkt-product-tour.js — self-paced, click-to-advance product tour.
 *
 * Wires every [data-mkt-tour] block: prev/next buttons, step dots, keyboard
 * arrows, touch swipe, URL sync (?tour=<slug>&step=N), and an idle "next" pulse
 * cue when the tour is in view (respecting prefers-reduced-motion). Vanilla,
 * framework-free, no inline handlers, defensive against missing elements.
 */
(function () {
  "use strict";

  if (typeof document === "undefined" || !document.querySelectorAll) {
    return;
  }

  var IDLE_PULSE_MS = 4500;
  var SWIPE_THRESHOLD_PX = 40;

  function prefersReducedMotion() {
    try {
      return (
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      );
    } catch (err) {
      return false;
    }
  }

  function clamp(value, min, max) {
    if (value < min) {
      return min;
    }
    if (value > max) {
      return max;
    }
    return value;
  }

  function initTour(root) {
    if (!root || root.__mktTourReady) {
      return;
    }
    root.__mktTourReady = true;

    var slug = root.getAttribute("data-mkt-tour-slug") || "";
    var frames = Array.prototype.slice.call(
      root.querySelectorAll("[data-mkt-tour-frame]")
    );
    if (!frames.length) {
      return;
    }
    var dots = Array.prototype.slice.call(
      root.querySelectorAll("[data-mkt-tour-dot]")
    );
    var prevBtn = root.querySelector("[data-mkt-tour-prev]");
    var nextBtn = root.querySelector("[data-mkt-tour-next]");

    var lastIndex = frames.length - 1;
    var current = 0;
    var hasInteracted = false;
    var idleTimer = null;
    var reduced = prefersReducedMotion();

    function clearPulse() {
      if (nextBtn) {
        nextBtn.classList.remove("mkt-tour__next--pulse");
      }
    }

    function syncUrl(index) {
      if (!slug || !window.history || typeof window.history.replaceState !== "function") {
        return;
      }
      try {
        var url = new URL(window.location.href);
        url.searchParams.set("tour", slug);
        url.searchParams.set("step", String(index + 1));
        window.history.replaceState(window.history.state, "", url.toString());
      } catch (err) {
        /* URL unsupported / cross-origin sandbox — skip silently. */
      }
    }

    function show(index, opts) {
      var target = clamp(index, 0, lastIndex);
      current = target;
      frames.forEach(function (frame, i) {
        var active = i === target;
        frame.classList.toggle("is-active", active);
        frame.setAttribute("aria-hidden", active ? "false" : "true");
        var tip = frame.querySelector("[data-mkt-tour-tooltip]");
        if (tip) {
          if (active) {
            tip.removeAttribute("hidden");
          } else {
            tip.setAttribute("hidden", "hidden");
          }
        }
      });
      dots.forEach(function (dot, i) {
        var active = i === target;
        dot.classList.toggle("is-active", active);
        if (active) {
          dot.setAttribute("aria-current", "true");
        } else {
          dot.removeAttribute("aria-current");
        }
      });
      if (prevBtn) {
        prevBtn.disabled = target === 0;
      }
      if (nextBtn) {
        nextBtn.disabled = target === lastIndex;
      }
      if (!opts || opts.sync !== false) {
        syncUrl(target);
      }
    }

    function markInteracted() {
      hasInteracted = true;
      clearPulse();
      if (idleTimer) {
        window.clearTimeout(idleTimer);
        idleTimer = null;
      }
    }

    function go(delta) {
      markInteracted();
      show(current + delta);
    }

    if (prevBtn) {
      prevBtn.addEventListener("click", function () {
        go(-1);
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        go(1);
      });
    }
    dots.forEach(function (dot, i) {
      dot.addEventListener("click", function () {
        markInteracted();
        show(i);
      });
    });

    root.addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        go(1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        go(-1);
      }
    });

    var touchStartX = null;
    var stage = root.querySelector("[data-mkt-tour-stage]") || root;
    stage.addEventListener(
      "touchstart",
      function (event) {
        if (event.touches && event.touches.length === 1) {
          touchStartX = event.touches[0].clientX;
        } else {
          touchStartX = null;
        }
      },
      { passive: true }
    );
    stage.addEventListener(
      "touchend",
      function (event) {
        if (touchStartX === null || !event.changedTouches || !event.changedTouches.length) {
          return;
        }
        var deltaX = event.changedTouches[0].clientX - touchStartX;
        touchStartX = null;
        if (Math.abs(deltaX) < SWIPE_THRESHOLD_PX) {
          return;
        }
        go(deltaX < 0 ? 1 : -1);
      },
      { passive: true }
    );

    function armIdlePulse() {
      if (reduced || hasInteracted || !nextBtn) {
        return;
      }
      if (idleTimer) {
        window.clearTimeout(idleTimer);
      }
      idleTimer = window.setTimeout(function () {
        if (!hasInteracted && nextBtn && current < lastIndex) {
          nextBtn.classList.add("mkt-tour__next--pulse");
        }
      }, IDLE_PULSE_MS);
    }

    if (typeof window.IntersectionObserver === "function") {
      try {
        var io = new window.IntersectionObserver(
          function (entries) {
            entries.forEach(function (entry) {
              if (entry.isIntersecting) {
                armIdlePulse();
              } else {
                clearPulse();
                if (idleTimer) {
                  window.clearTimeout(idleTimer);
                  idleTimer = null;
                }
              }
            });
          },
          { threshold: 0.4 }
        );
        io.observe(root);
      } catch (err) {
        /* IO constructor unsupported — graceful no-op. */
      }
    }

    // Restore from URL (?tour=<slug>&step=N) on load, else start at frame 0.
    var startIndex = 0;
    try {
      var params = new URL(window.location.href).searchParams;
      if (params.get("tour") === slug) {
        var step = parseInt(params.get("step"), 10);
        if (!isNaN(step)) {
          startIndex = clamp(step - 1, 0, lastIndex);
        }
      }
    } catch (err) {
      startIndex = 0;
    }
    show(startIndex, { sync: false });
  }

  function initAll() {
    var roots = document.querySelectorAll("[data-mkt-tour]");
    Array.prototype.forEach.call(roots, initTour);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
