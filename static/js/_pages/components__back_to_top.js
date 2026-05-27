/**
 * RunMyCampus back-to-top — scroll progress, fold threshold, assist-dock stacking.
 */
(function () {
  "use strict";

  var THRESHOLD_FOLDS = 2;
  var THRESHOLD_FOLDS_CANVAS = 1;
  var MIN_PX_CANVAS = 280;
  var state = {
    btn: null,
    progressCircle: null,
    percentEl: null,
    ticking: false,
    bound: false,
  };

  function foldHeight() {
    return window.RMC && window.RMC.getFoldHeight
      ? window.RMC.getFoldHeight()
      : Math.max(window.innerHeight || 0, 320);
  }

  function scrollThreshold() {
    var body = document.body;
    var mode = body && body.getAttribute("data-rmc-cp-scroll");
    if (mode === "canvas") {
      return Math.max(MIN_PX_CANVAS, foldHeight() * THRESHOLD_FOLDS_CANVAS);
    }
    return foldHeight() * THRESHOLD_FOLDS;
  }

  function getScrollContainer() {
    return window.RMC && window.RMC.getScrollContainer
      ? window.RMC.getScrollContainer()
      : null;
  }

  function getScrollTop(container) {
    return window.RMC && window.RMC.getScrollTop
      ? window.RMC.getScrollTop(container)
      : container
        ? container.scrollTop
        : window.scrollY || document.documentElement.scrollTop;
  }

  function getScrollMetrics(container) {
    if (container) {
      return {
        top: container.scrollTop,
        max: Math.max(container.scrollHeight - container.clientHeight, 0),
      };
    }
    var doc = document.documentElement;
    return {
      top: window.scrollY || doc.scrollTop || 0,
      max: Math.max(doc.scrollHeight - window.innerHeight, 0),
    };
  }

  function scrollProgress(container) {
    var metrics = getScrollMetrics(container);
    if (metrics.max <= 0) return 0;
    return Math.min(1, Math.max(0, metrics.top / metrics.max));
  }

  function scrollToTop() {
    var container = getScrollContainer();
    if (window.RMC && window.RMC.scrollToY) {
      window.RMC.scrollToY(container, 0, "smooth");
    } else if (container) {
      container.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    state.btn.classList.add("rmc-back-to-top--launching");
    window.setTimeout(function () {
      if (state.btn) state.btn.classList.remove("rmc-back-to-top--launching");
    }, 520);
  }

  function syncGradientStops() {
    if (!state.btn) return;
    var root = document.documentElement;
    var style = window.getComputedStyle(root);
    var primary = style.getPropertyValue("--school-primary").trim() || "#4f46e5";
    var accent =
      style.getPropertyValue("--school-accent").trim() ||
      style.getPropertyValue("--mkt-accent").trim() ||
      "#10b981";
    var stops = document.querySelectorAll(".rmc-back-to-top-gradient-stop");
    if (stops.length >= 2) {
      stops[0].setAttribute("stop-color", primary);
      stops[1].setAttribute("stop-color", accent);
    }
    state.btn.style.setProperty("--rmc-back-to-top-primary", primary);
    state.btn.style.setProperty("--rmc-back-to-top-accent", accent);
  }

  function renderProgress(progress) {
    var pct = Math.round(progress * 100);
    state.btn.style.setProperty("--rmc-back-to-top-progress", String(progress));
    if (state.progressCircle) {
      state.progressCircle.style.strokeDashoffset = String(1 - progress);
      state.progressCircle.setAttribute("aria-valuenow", String(pct));
    }
    if (state.percentEl) {
      state.percentEl.textContent = String(pct);
    }
    state.btn.setAttribute("data-rmc-back-to-top-progress", String(pct));
  }

  function update() {
    state.ticking = false;
    if (!state.btn) return;

    var container = getScrollContainer();
    var top = getScrollTop(container);
    var visible = top >= scrollThreshold();
    var progress = scrollProgress(container);

    renderProgress(progress);

    if (visible) {
      state.btn.removeAttribute("hidden");
      state.btn.setAttribute("aria-hidden", "false");
      state.btn.classList.add("rmc-back-to-top--visible");
      document.documentElement.setAttribute("data-rmc-back-to-top-armed", "1");
    } else {
      state.btn.setAttribute("hidden", "");
      state.btn.setAttribute("aria-hidden", "true");
      state.btn.classList.remove("rmc-back-to-top--visible");
      document.documentElement.removeAttribute("data-rmc-back-to-top-armed");
    }
  }

  function scheduleUpdate() {
    if (state.ticking) return;
    state.ticking = true;
    window.requestAnimationFrame(update);
  }

  function bindListeners() {
    if (state.bound || !state.btn) return;
    state.bound = true;

    var container = getScrollContainer();
    if (container) {
      container.addEventListener("scroll", scheduleUpdate, { passive: true });
    }
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate, { passive: true });
    state.btn.addEventListener("click", scrollToTop);

    document.addEventListener("rmc-assist-dock-mounted", scheduleUpdate);
    document.body.addEventListener("htmx:afterSettle", scheduleUpdate);
    document.body.addEventListener("htmx:afterSwap", scheduleUpdate);

    window.addEventListener("keydown", function (event) {
      if (
        event.key === "Home" &&
        event.altKey &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.shiftKey &&
        state.btn &&
        !state.btn.hasAttribute("hidden")
      ) {
        event.preventDefault();
        scrollToTop();
      }
    });
  }

  function ensureBodyMounted(btn) {
    if (!btn || btn.parentElement === document.body) return;
    if (btn.closest(".rmc-app-shell")) {
      document.body.appendChild(btn);
    }
  }

  function mount() {
    var btn = document.getElementById("back-to-top-btn");
    if (!btn || btn.getAttribute("data-rmc-mounted") === "1") return false;

    ensureBodyMounted(btn);
    state.btn = btn;
    state.progressCircle = btn.querySelector(".rmc-back-to-top__progress");
    state.percentEl = btn.querySelector("[data-rmc-back-to-top-percent]");
    btn.setAttribute("data-rmc-mounted", "1");

    syncGradientStops();
    bindListeners();
    scheduleUpdate();
    return true;
  }

  window.RMCBackToTop = {
    refresh: scheduleUpdate,
    mount: mount,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
