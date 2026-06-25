/**
 * Lazy-load world-globe.mount.js when globe JSON is present.
 * Operator toggle: Live (WebGL when available) vs Offline (regional SVG only).
 * SVG lives in #rmc-world-globe-stage so globe.gl init cannot wipe fallback markup.
 */
(function () {
  if (window.__rmcWorldGlobeLoader) {
    return;
  }
  window.__rmcWorldGlobeLoader = true;

  var MODE_KEY = "rmc-globe-display-mode";
  var MODE_LIVE = "live";
  var MODE_OFFLINE = "offline";

  function currentScriptSrc() {
    var scripts = document.getElementsByTagName("script");
    for (var i = scripts.length - 1; i >= 0; i -= 1) {
      var s = scripts[i];
      if (s && s.getAttribute && s.getAttribute("data-rmc-world-globe-loader") === "1") {
        return s.getAttribute("data-rmc-mount-src") || "";
      }
    }
    return "";
  }

  function globeMount() {
    return document.getElementById("rmc-world-globe");
  }

  function globeStage() {
    var mount = globeMount();
    if (!mount) {
      return null;
    }
    return (
      document.getElementById("rmc-world-globe-stage") ||
      mount.closest(".lx-world__globe-stage") ||
      mount.parentElement
    );
  }

  function globeAlreadyMounted() {
    var c = globeMount();
    return !!(c && c.getAttribute("data-rmc-world-globe-inited") === "1");
  }

  function getOperatorMode() {
    try {
      var stored = window.sessionStorage.getItem(MODE_KEY);
      if (stored === MODE_OFFLINE || stored === MODE_LIVE) {
        return stored;
      }
    } catch (_err) {
      /* sessionStorage blocked */
    }
    return MODE_LIVE;
  }

  function setOperatorMode(mode) {
    var next = mode === MODE_OFFLINE ? MODE_OFFLINE : MODE_LIVE;
    try {
      window.sessionStorage.setItem(MODE_KEY, next);
    } catch (_err) {
      /* ignore */
    }
    var stage = globeStage();
    if (stage) {
      stage.setAttribute("data-rmc-globe-operator-mode", next);
    }
    syncModeToggleUi(next);
    return next;
  }

  function syncModeToggleUi(mode) {
    var liveBtn = document.getElementById("rmc-world-globe-mode-live");
    var offlineBtn = document.getElementById("rmc-world-globe-mode-offline");
    var isLive = mode !== MODE_OFFLINE;
    if (liveBtn) {
      liveBtn.classList.toggle("on", isLive);
      liveBtn.setAttribute("aria-pressed", isLive ? "true" : "false");
    }
    if (offlineBtn) {
      offlineBtn.classList.toggle("on", !isLive);
      offlineBtn.setAttribute("aria-pressed", !isLive ? "true" : "false");
    }
  }

  function isSvgOfflineMode() {
    if (getOperatorMode() === MODE_OFFLINE) {
      return true;
    }
    var stage = globeStage();
    if (!stage) return false;
    return (
      stage.getAttribute("data-rmc-globe-mode") === "svg-offline" ||
      stage.classList.contains("lx-world__globe--offline")
    );
  }

  function isNavigatorOffline() {
    return typeof navigator !== "undefined" && navigator.onLine === false;
  }

  function shouldSkipHeavyGlobe() {
    if (getOperatorMode() === MODE_OFFLINE) {
      return true;
    }
    if (isNavigatorOffline()) {
      return true;
    }
    var root = document.documentElement;
    if (root && root.getAttribute("data-rmc-low-bandwidth") === "1") {
      return true;
    }
    var conn = navigator && navigator.connection;
    if (conn && conn.saveData === true) {
      return true;
    }
    return false;
  }

  function removeMountScript() {
    var mountTag = document.querySelector('script[data-rmc-world-globe-mount="1"]');
    if (mountTag) {
      mountTag.remove();
    }
  }

  function ensureSvgVisible() {
    var stage = globeStage();
    if (!stage) {
      return;
    }
    var svg = stage.querySelector(".lx-world__svg-fallback");
    if (svg) {
      svg.hidden = false;
      svg.removeAttribute("hidden");
    }
  }

  function markOfflineFallback() {
    var mount = globeMount();
    var stage = globeStage();
    if (!mount || !stage) {
      return;
    }
    removeMountScript();
    stage.classList.add("lx-world__globe--fallback", "lx-world__globe--offline", "lx-world__globe--revealed");
    stage.setAttribute("data-rmc-globe-mode", "svg-offline");
    stage.classList.remove("lx-world__globe--webgl-ready");
    mount.classList.remove("lx-world__globe--webgl-ready");
    mount.removeAttribute("data-rmc-world-globe-inited");
    ensureSvgVisible();
    var canvas = mount.querySelector("canvas");
    if (canvas) {
      canvas.remove();
    }
    var note = document.getElementById("rmc-world-globe-offline-note");
    if (note) {
      note.hidden = getOperatorMode() !== MODE_OFFLINE;
    }
    var sk = stage.closest(".lx-world__map");
    if (sk) {
      var skeleton = sk.querySelector(".lx-world__globe-skeleton");
      if (skeleton) skeleton.remove();
    }
    document.dispatchEvent(new CustomEvent("rmc:globe-offline-fallback"));
  }

  function clearOfflineModeForRetry() {
    var mount = globeMount();
    var stage = globeStage();
    if (!mount || !stage) {
      return;
    }
    stage.classList.remove("lx-world__globe--fallback", "lx-world__globe--offline");
    stage.removeAttribute("data-rmc-globe-mode");
    var note = document.getElementById("rmc-world-globe-offline-note");
    if (note) {
      note.hidden = true;
    }
  }

  function loadMountBundle() {
    var mount = globeMount();
    var stage = globeStage();
    if (!mount || !stage) {
      return;
    }
    ensureSvgVisible();

    if (shouldSkipHeavyGlobe()) {
      markOfflineFallback();
      return;
    }

    var dataEl = document.getElementById("rmc-world-globe-data");
    if (!dataEl || !dataEl.textContent || !dataEl.textContent.trim()) {
      markOfflineFallback();
      return;
    }
    var mountSrc = currentScriptSrc();
    if (!mountSrc) {
      markOfflineFallback();
      return;
    }
    if (document.querySelector('script[data-rmc-world-globe-mount="1"]')) {
      return;
    }

    clearOfflineModeForRetry();

    var tag = document.createElement("script");
    tag.type = "module";
    tag.src = mountSrc;
    tag.setAttribute("data-rmc-world-globe-mount", "1");
    var loadTimeout = window.setTimeout(function () {
      if (!globeAlreadyMounted()) {
        markOfflineFallback();
      }
    }, 12000);
    tag.addEventListener("load", function () {
      if (shouldSkipHeavyGlobe()) {
        window.clearTimeout(loadTimeout);
        markOfflineFallback();
        return;
      }
      var watch = window.setInterval(function () {
        if (shouldSkipHeavyGlobe()) {
          window.clearInterval(watch);
          window.clearTimeout(loadTimeout);
          markOfflineFallback();
          return;
        }
        if (globeAlreadyMounted()) {
          window.clearInterval(watch);
          window.clearTimeout(loadTimeout);
          document.dispatchEvent(new CustomEvent("rmc:globe-ready"));
        }
      }, 250);
    });
    tag.addEventListener("error", function () {
      window.clearTimeout(loadTimeout);
      markOfflineFallback();
    });
    document.head.appendChild(tag);
  }

  function applyOperatorMode(mode) {
    setOperatorMode(mode);
    document.dispatchEvent(
      new CustomEvent("rmc:globe-operator-mode", { detail: { mode: mode } })
    );
    if (mode === MODE_OFFLINE) {
      markOfflineFallback();
      return;
    }
    if (isNavigatorOffline()) {
      markOfflineFallback();
      return;
    }
    clearOfflineModeForRetry();
    loadMountBundle();
  }

  function wireModeToggle() {
    var toggle = document.getElementById("rmc-world-globe-mode-toggle");
    if (!toggle || toggle.getAttribute("data-rmc-globe-mode-wired") === "1") {
      return;
    }
    toggle.setAttribute("data-rmc-globe-mode-wired", "1");
    var liveBtn = document.getElementById("rmc-world-globe-mode-live");
    var offlineBtn = document.getElementById("rmc-world-globe-mode-offline");
    if (liveBtn) {
      liveBtn.addEventListener("click", function () {
        applyOperatorMode(MODE_LIVE);
      });
    }
    if (offlineBtn) {
      offlineBtn.addEventListener("click", function () {
        applyOperatorMode(MODE_OFFLINE);
      });
    }
    syncModeToggleUi(getOperatorMode());
  }

  function retryMountWhenOnline() {
    if (getOperatorMode() === MODE_OFFLINE) {
      markOfflineFallback();
      return;
    }
    if (shouldSkipHeavyGlobe()) {
      markOfflineFallback();
      return;
    }
    if (globeAlreadyMounted()) {
      return;
    }
    clearOfflineModeForRetry();
    loadMountBundle();
  }

  function initGlobeLoader() {
    var stage = globeStage();
    if (stage) {
      stage.setAttribute("data-rmc-globe-operator-mode", getOperatorMode());
    }
    wireModeToggle();
    if (getOperatorMode() === MODE_OFFLINE) {
      markOfflineFallback();
      return;
    }
    loadMountBundle();
  }

  window.RMCWorldGlobeLoader = {
    getMode: getOperatorMode,
    setMode: applyOperatorMode,
    retryMount: retryMountWhenOnline,
  };

  if (typeof window !== "undefined") {
    window.addEventListener("offline", function () {
      markOfflineFallback();
    });
    window.addEventListener("online", retryMountWhenOnline);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGlobeLoader);
  } else {
    initGlobeLoader();
  }
})();
