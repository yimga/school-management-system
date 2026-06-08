/**
 * RunMyCampus bounded layout observability.
 *
 * Measures platform surfaces without reading content or changing layout.
 * The public snapshot contains only counts, pixel deltas, viewport class,
 * direction, and visual viewport dimensions.
 */
(function () {
  "use strict";

  if (window.rmcLayoutObserver) return;

  var MAX_ELEMENTS = 160;
  var OVERFLOW_TOLERANCE_PX = 2;
  var SELECTOR = [
    "[data-rmc-layout-observe]",
    ".table-responsive",
    ".rmc-data-table-wrapper",
    "[data-rmc-operational-workbench]"
  ].join(",");
  var states = new Map();
  var resizeObserver = null;
  var mutationObserver = null;
  var scanQueued = false;
  var stopped = false;

  function boundedDimension(value) {
    var number = Math.round(Number(value) || 0);
    return Math.max(0, Math.min(number, 100000));
  }

  function viewportClass() {
    var value = document.documentElement.getAttribute("data-rmc-viewport-class");
    return value === "A" || value === "B" || value === "C" ? value : "U";
  }

  function direction() {
    return document.documentElement.getAttribute("dir") === "rtl" ? "rtl" : "ltr";
  }

  function measure(element) {
    if (!element || !element.isConnected) {
      states.delete(element);
      return;
    }
    var inlineDelta = Math.max(0, element.scrollWidth - element.clientWidth);
    var observeMode = element.getAttribute("data-rmc-layout-observe") || "inline";
    var blockDelta = observeMode === "clip"
      ? Math.max(0, element.scrollHeight - element.clientHeight)
      : 0;
    var inlineOverflow = inlineDelta > OVERFLOW_TOLERANCE_PX;
    var blockOverflow = blockDelta > OVERFLOW_TOLERANCE_PX;
    var overflow = inlineOverflow || blockOverflow;

    states.set(element, {
      inline: inlineOverflow ? boundedDimension(inlineDelta) : 0,
      block: blockOverflow ? boundedDimension(blockDelta) : 0
    });

    if (overflow) {
      element.setAttribute(
        "data-rmc-layout-overflow",
        inlineOverflow && blockOverflow ? "both" : (inlineOverflow ? "inline" : "block")
      );
    } else {
      element.removeAttribute("data-rmc-layout-overflow");
    }
  }

  function pruneAndMeasure() {
    states.forEach(function (_state, element) {
      if (!element.isConnected) states.delete(element);
    });
    document.querySelectorAll(SELECTOR).forEach(function (element) {
      if (!states.has(element) && states.size >= MAX_ELEMENTS) return;
      if (!states.has(element) && resizeObserver) resizeObserver.observe(element);
      measure(element);
    });
    emit();
  }

  function scheduleScan() {
    if (scanQueued || stopped) return;
    scanQueued = true;
    var schedule = window.requestAnimationFrame || function (callback) {
      return window.setTimeout(callback, 16);
    };
    schedule(function () {
      scanQueued = false;
      pruneAndMeasure();
    });
  }

  function snapshot() {
    var overflowCount = 0;
    var inlineCount = 0;
    var blockCount = 0;
    var maxInline = 0;
    var maxBlock = 0;
    states.forEach(function (state) {
      if (state.inline || state.block) overflowCount += 1;
      if (state.inline) inlineCount += 1;
      if (state.block) blockCount += 1;
      maxInline = Math.max(maxInline, state.inline);
      maxBlock = Math.max(maxBlock, state.block);
    });
    var visual = window.visualViewport;
    return {
      version: 1,
      observed_count: states.size,
      overflow_count: overflowCount,
      inline_overflow_count: inlineCount,
      block_overflow_count: blockCount,
      max_inline_overflow_px: maxInline,
      max_block_overflow_px: maxBlock,
      viewport_class: viewportClass(),
      direction: direction(),
      visual_viewport_width: boundedDimension(visual ? visual.width : window.innerWidth),
      visual_viewport_height: boundedDimension(visual ? visual.height : window.innerHeight)
    };
  }

  function emit() {
    try {
      document.dispatchEvent(new CustomEvent("rmc:layout-observation", {
        detail: snapshot()
      }));
    } catch (_error) {}
  }

  function init() {
    if (typeof ResizeObserver === "function") {
      resizeObserver = new ResizeObserver(function (entries) {
        entries.forEach(function (entry) { measure(entry.target); });
        emit();
      });
    }
    if (typeof MutationObserver === "function" && document.body) {
      mutationObserver = new MutationObserver(scheduleScan);
      mutationObserver.observe(document.body, {
        childList: true,
        subtree: true
      });
    }
    window.addEventListener("resize", scheduleScan, { passive: true });
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", scheduleScan, { passive: true });
    }
    scheduleScan();
  }

  window.rmcLayoutObserver = {
    getSnapshot: snapshot,
    rescan: scheduleScan,
    stop: function () {
      stopped = true;
      if (resizeObserver) resizeObserver.disconnect();
      if (mutationObserver) mutationObserver.disconnect();
      window.removeEventListener("resize", scheduleScan);
      if (window.visualViewport) {
        window.visualViewport.removeEventListener("resize", scheduleScan);
      }
      states.clear();
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
