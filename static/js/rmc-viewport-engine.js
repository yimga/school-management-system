// RunMyCampus viewport engine (v4.00.0).
//
// Boot-time classifier. Reads hardware/network telemetry and stamps the
// resulting viewport class onto <html data-rmc-viewport-class="A|B|C">.
// CSS in static/css/rmc-viewport-engine.css consumes the attribute to
// run the three structural DOM strategies (multi-column / orb / voice).
//
// Anti-pattern killed: media queries that only shrink. This engine also
// strips/blocks heavy modules on Viewport C and pre-warms cross-record
// drawers on Viewport A.
//
// Honors the existing low-power.js + sync-manager.js telemetry without
// duplicating it — emits a `rmc:viewport-class-change` CustomEvent that
// those modules already listen for.

(function () {
  "use strict";
  if (window.rmcViewport) return;

  const HTML = document.documentElement;
  const ATTR = "data-rmc-viewport-class";
  const EVENT = "rmc:viewport-class-change";

  function probeNetwork() {
    const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!c) return { effectiveType: "4g", saveData: false, downlink: 10 };
    return {
      effectiveType: c.effectiveType || "4g",
      saveData: !!c.saveData,
      downlink: typeof c.downlink === "number" ? c.downlink : 10,
    };
  }

  function probeHardware() {
    return {
      cores: navigator.hardwareConcurrency || 4,
      memory: navigator.deviceMemory || 4,
      touch: navigator.maxTouchPoints > 0,
    };
  }

  function probeViewport() {
    const visual = window.visualViewport;
    return {
      w: visual ? visual.width : (window.innerWidth || 0),
      h: visual ? visual.height : (window.innerHeight || 0),
      pixelRatio: window.devicePixelRatio || 1,
    };
  }

  function publishViewportMeasurements() {
    const v = probeViewport();
    HTML.style.setProperty("--rmc-viewport-width-px", `${Math.round(v.w)}px`);
    HTML.style.setProperty("--rmc-viewport-height-px", `${Math.round(v.h)}px`);
  }

  function classify() {
    const net = probeNetwork();
    const hw = probeHardware();
    const v = probeViewport();
    // Viewport C — low-end smartphone / parent stream
    if (
      v.w <= 600 ||
      hw.cores <= 4 && hw.memory <= 2 ||
      net.saveData ||
      net.effectiveType === "slow-2g" || net.effectiveType === "2g" || net.effectiveType === "3g"
    ) {
      return "C";
    }
    // Viewport A — desktop/4K command center
    if (v.w >= 1600 && hw.cores >= 8 && hw.memory >= 4) return "A";
    // Viewport B — tablet / Chromebook
    return "B";
  }

  function apply(cls) {
    const prev = HTML.getAttribute(ATTR);
    if (prev === cls) return;
    HTML.setAttribute(ATTR, cls);
    // Hard-throttle on Viewport C: drop heavy modules that haven't booted yet.
    if (cls === "C") {
      HTML.setAttribute("data-rmc-low-power", "1");
      HTML.setAttribute("data-rmc-no-charts", "1");
      HTML.setAttribute("data-rmc-no-animations", "1");
    } else if (prev === "C") {
      HTML.removeAttribute("data-rmc-no-charts");
      HTML.removeAttribute("data-rmc-no-animations");
    }
    document.dispatchEvent(new CustomEvent(EVENT, { detail: { cls, prev } }));
  }

  function debounce(fn, ms) {
    let t;
    return function () {
      clearTimeout(t);
      t = setTimeout(fn, ms);
    };
  }

  function reclassify() {
    publishViewportMeasurements();
    apply(classify());
  }

  // SSR-stamped attribute (if any) is the first-paint hint; immediately re-classify
  // on real telemetry post-boot.
  reclassify();
  window.addEventListener("resize", debounce(reclassify, 250));
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", debounce(reclassify, 100));
  }
  if ("connection" in navigator) {
    try { navigator.connection.addEventListener("change", reclassify); } catch {}
  }

  // Public API for cooperative modules.
  window.rmcViewport = {
    current: () => HTML.getAttribute(ATTR) || classify(),
    measurements: probeViewport,
    reclassify,
    onChange: (cb) => {
      const handler = (e) => { try { cb(e.detail); } catch {} };
      document.addEventListener(EVENT, handler);
      return () => document.removeEventListener(EVENT, handler);
    },
  };
})();
