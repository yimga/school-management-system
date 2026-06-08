/**
 * Lazy-load world-globe.mount.js (single-file ES module) when globe JSON is present.
 * Offline: SVG fallback is visible immediately; WebGL is progressive enhancement only.
 * Skips WebGL on offline / low-bandwidth / Save-Data / forced svg-offline mode.
 * SVG lives in #rmc-world-globe-stage (sibling of #rmc-world-globe) so globe.gl init
 * cannot wipe the fallback markup.
 */
(function () {
  if (window.__rmcWorldGlobeLoader) {
    return;
  }
  window.__rmcWorldGlobeLoader = true;

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

  function isSvgOfflineMode() {
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
      note.hidden = false;
    }
    var sk = stage.closest(".lx-world__map");
    if (sk) {
      var skeleton = sk.querySelector(".lx-world__globe-skeleton");
      if (skeleton) skeleton.remove();
    }
    document.dispatchEvent(new CustomEvent("rmc:globe-offline-fallback"));
  }

  function loadMountBundle() {
    var mount = globeMount();
    var stage = globeStage();
    if (!mount || !stage) {
      return;
    }
    ensureSvgVisible();

    if (isSvgOfflineMode()) {
      markOfflineFallback();
      return;
    }

    var dataEl = document.getElementById("rmc-world-globe-data");
    if (!dataEl || !dataEl.textContent || !dataEl.textContent.trim()) {
      markOfflineFallback();
      return;
    }
    if (shouldSkipHeavyGlobe()) {
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
      if (isSvgOfflineMode()) {
        window.clearTimeout(loadTimeout);
        markOfflineFallback();
        return;
      }
      var watch = window.setInterval(function () {
        if (isSvgOfflineMode()) {
          window.clearInterval(watch);
          window.clearTimeout(loadTimeout);
          markOfflineFallback();
          return;
        }
        if (globeAlreadyMounted()) {
          window.clearInterval(watch);
          window.clearTimeout(loadTimeout);
        }
      }, 250);
    });
    tag.addEventListener("error", function () {
      window.clearTimeout(loadTimeout);
      markOfflineFallback();
    });
    document.head.appendChild(tag);
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

  function retryMountWhenOnline() {
    if (shouldSkipHeavyGlobe()) {
      return;
    }
    if (globeAlreadyMounted()) {
      return;
    }
    if (!isSvgOfflineMode()) {
      return;
    }
    clearOfflineModeForRetry();
    loadMountBundle();
  }

  if (typeof window !== "undefined") {
    window.addEventListener("offline", markOfflineFallback);
    window.addEventListener("online", retryMountWhenOnline);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadMountBundle);
  } else {
    loadMountBundle();
  }
})();
