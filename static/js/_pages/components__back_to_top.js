/**
 * RunMyCampus back-to-top — scroll progress, fold threshold, assist-dock stacking.
 */
(function () {
  "use strict";

  var THRESHOLD_FOLDS = 1;
  var THRESHOLD_FOLDS_CANVAS = 0.35;
  var MIN_PX_CANVAS = 120;
  var state = {
    btn: null,
    progressCircle: null,
    percentEl: null,
    ticking: false,
    bound: false,
    drag: null,
    suppressClickUntil: 0,
  };
  var STORAGE_KEY = "rmc.back_to_top.position.v1";

  function foldHeight() {
    return window.RMC && window.RMC.getFoldHeight
      ? window.RMC.getFoldHeight()
      : Math.max(window.innerHeight || 0, 320);
  }

  function alwaysVisiblePolicy() {
    var body = document.body;
    if (!body) return false;
    if (body.getAttribute("data-rmc-back-to-top-policy") === "always") {
      return true;
    }
    var root = document.documentElement;
    return root && root.getAttribute("data-rmc-back-to-top-policy") === "always";
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

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function savePosition(right, bottom) {
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          right: Math.round(right),
          bottom: Math.round(bottom),
        })
      );
    } catch (e) {
      /* no-op: storage unavailable */
    }
  }

  function clearSavedPosition() {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      /* no-op: storage unavailable */
    }
  }

  function loadPosition() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return null;
      if (typeof parsed.right !== "number" || typeof parsed.bottom !== "number") {
        return null;
      }
      return { right: parsed.right, bottom: parsed.bottom };
    } catch (e) {
      return null;
    }
  }

  function applyPosition(right, bottom) {
    if (!state.btn) return;
    state.btn.style.right = Math.round(right) + "px";
    state.btn.style.bottom = Math.round(bottom) + "px";
  }

  function applySavedPosition() {
    if (!state.btn) return;
    var saved = loadPosition();
    if (!saved) return;
    var rect = state.btn.getBoundingClientRect();
    var width = Math.max(rect.width, 40);
    var height = Math.max(rect.height, 40);
    var maxRight = Math.max(window.innerWidth - width - 4, 4);
    var maxBottom = Math.max(window.innerHeight - height - 4, 4);
    applyPosition(clamp(saved.right, 4, maxRight), clamp(saved.bottom, 4, maxBottom));
  }

  function resetPosition(event) {
    if (!state.btn) return;
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    clearSavedPosition();
    state.btn.style.removeProperty("right");
    state.btn.style.removeProperty("bottom");
    state.suppressClickUntil = Date.now() + 260;
    scheduleUpdate();
  }

  function startDrag(event) {
    if (!state.btn || event.button !== 0) return;
    var rect = state.btn.getBoundingClientRect();
    state.drag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startLeft: rect.left,
      startTop: rect.top,
      moved: false,
    };
    state.btn.classList.add("rmc-back-to-top--dragging");
    try {
      state.btn.setPointerCapture(event.pointerId);
    } catch (e) {
      /* no-op: unsupported environment */
    }
  }

  function moveDrag(event) {
    if (!state.btn || !state.drag) return;
    if (event.pointerId !== state.drag.pointerId) return;
    var dx = event.clientX - state.drag.startX;
    var dy = event.clientY - state.drag.startY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
      state.drag.moved = true;
    }
    var rect = state.btn.getBoundingClientRect();
    var width = Math.max(rect.width, 40);
    var height = Math.max(rect.height, 40);
    var nextLeft = clamp(state.drag.startLeft + dx, 4, window.innerWidth - width - 4);
    var nextTop = clamp(state.drag.startTop + dy, 4, window.innerHeight - height - 4);
    var nextRight = window.innerWidth - (nextLeft + width);
    var nextBottom = window.innerHeight - (nextTop + height);
    applyPosition(nextRight, nextBottom);
  }

  function endDrag(event) {
    if (!state.btn || !state.drag) return;
    if (event.pointerId !== state.drag.pointerId) return;
    var dragState = state.drag;
    state.drag = null;
    state.btn.classList.remove("rmc-back-to-top--dragging");
    try {
      if (state.btn.hasPointerCapture && state.btn.hasPointerCapture(event.pointerId)) {
        state.btn.releasePointerCapture(event.pointerId);
      }
    } catch (e) {
      /* no-op: unsupported environment */
    }
    if (dragState.moved) {
      var rect = state.btn.getBoundingClientRect();
      var right = window.innerWidth - (rect.left + rect.width);
      var bottom = window.innerHeight - (rect.top + rect.height);
      savePosition(right, bottom);
      state.suppressClickUntil = Date.now() + 280;
    }
  }

  function handleClick(event) {
    if (Date.now() < state.suppressClickUntil) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    scrollToTop();
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
    var scrolled = top >= scrollThreshold();
    var progress = scrollProgress(container);
    var alwaysOn = alwaysVisiblePolicy();

    renderProgress(progress);

    if (alwaysOn || scrolled) {
      state.btn.removeAttribute("hidden");
      state.btn.setAttribute("aria-hidden", "false");
      state.btn.classList.add("rmc-back-to-top--visible");
      if (alwaysOn && !scrolled) {
        state.btn.classList.add("rmc-back-to-top--idle");
      } else {
        state.btn.classList.remove("rmc-back-to-top--idle");
      }
      document.documentElement.setAttribute("data-rmc-back-to-top-armed", "1");
    } else {
      state.btn.setAttribute("hidden", "");
      state.btn.setAttribute("aria-hidden", "true");
      state.btn.classList.remove("rmc-back-to-top--visible");
      state.btn.classList.remove("rmc-back-to-top--idle");
      document.documentElement.removeAttribute("data-rmc-back-to-top-armed");
    }
  }

  function scheduleUpdate() {
    if (state.ticking) return;
    state.ticking = true;
    window.requestAnimationFrame(update);
  }

  function bindScrollTargets() {
    var seen = typeof WeakSet === "function" ? new WeakSet() : null;
    var attached = state.scrollTargets || (state.scrollTargets = []);
    function attach(el) {
      if (!el) return;
      if (seen) {
        if (seen.has(el)) return;
        seen.add(el);
      } else if (attached.indexOf(el) !== -1) {
        return;
      } else {
        attached.push(el);
      }
      el.addEventListener("scroll", scheduleUpdate, { passive: true });
    }
    var targets =
      window.RMC && window.RMC.getScrollListenerTargets
        ? window.RMC.getScrollListenerTargets()
        : [];
    var i;
    for (i = 0; i < targets.length; i += 1) {
      attach(targets[i]);
    }
    attach(getScrollContainer());
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
  }

  function bindListeners() {
    if (state.bound || !state.btn) return;
    state.bound = true;

    bindScrollTargets();
    window.addEventListener("resize", scheduleUpdate, { passive: true });
    window.addEventListener("resize", applySavedPosition, { passive: true });
    state.btn.addEventListener("click", handleClick);
    state.btn.addEventListener("contextmenu", resetPosition);
    state.btn.addEventListener("pointerdown", startDrag);
    state.btn.addEventListener("pointermove", moveDrag);
    state.btn.addEventListener("pointerup", endDrag);
    state.btn.addEventListener("pointercancel", endDrag);

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
    applySavedPosition();
    bindListeners();
    scheduleUpdate();
    return true;
  }

  window.RMCBackToTop = {
    refresh: scheduleUpdate,
    mount: mount,
  };

  function boot() {
    mount();
    scheduleUpdate();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.addEventListener("load", scheduleUpdate);

  if (typeof MutationObserver === "function") {
    var shellObserver = new MutationObserver(scheduleUpdate);
    var observeShell = function () {
      var shell = document.querySelector(".rmc-app-shell");
      if (shell) {
        shellObserver.observe(shell, { childList: true, subtree: true });
      }
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", observeShell);
    } else {
      observeShell();
    }
  }
})();
