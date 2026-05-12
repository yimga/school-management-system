/**
 * Shell polish — scroll-aware header + density preference bootstrap.
 *
 * Two small responsibilities:
 *  1. Add `.is-scrolled` to <html> when document is scrolled past 4px so the
 *     topbar can frost + condense via CSS. Removed when back at top.
 *  2. Apply persisted density preference (compact / comfortable / spacious) to
 *     <html data-rmc-density> before paint. Exposes `window.RMCDensity` for the
 *     user-facing toggle in the preferences page.
 *
 * Both honor prefers-reduced-motion when applicable.
 */
(function () {
  "use strict";

  /* ---------- Scroll-aware header ---------- */
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      var scrolled = (window.scrollY || document.documentElement.scrollTop) > 4;
      document.documentElement.classList.toggle("is-scrolled", scrolled);
      ticking = false;
    });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  /* Initial check (browsers restore scroll on back nav). */
  onScroll();

  /* ---------- Density preference ---------- */
  var KEY = "rmc-density";
  var VALID = { compact: 1, comfortable: 1, spacious: 1 };

  function read() {
    var raw = null;
    try { raw = localStorage.getItem(KEY); } catch (_) {}
    return VALID[raw] ? raw : "comfortable";
  }
  function apply(value) {
    if (!VALID[value]) value = "comfortable";
    if (value === "comfortable") {
      document.documentElement.removeAttribute("data-rmc-density");
    } else {
      document.documentElement.setAttribute("data-rmc-density", value);
    }
  }
  apply(read());

  window.RMCDensity = {
    get: read,
    set: function (value) {
      if (!VALID[value]) value = "comfortable";
      try { localStorage.setItem(KEY, value); } catch (_) {}
      apply(value);
      try { window.dispatchEvent(new CustomEvent("rmc:density-change", { detail: { value: value } })); } catch (_) {}
    }
  };

  /* Cross-tab sync. */
  window.addEventListener("storage", function (e) {
    if (e.key === KEY) apply(read());
  });

  /* ---------- Adaptive logo <img> swap ----------
     Markup contract (companion to .rmc-logo-adaptive CSS rule in design-tokens.css):
       <img class="rmc-logo-adaptive-img"
            src="{{ SITE_LOGO_URL }}"
            data-logo-light-src="{{ SITE_LOGO_URL }}"
            data-logo-dark-src="{{ SITE_LOGO_DARK_URL }}"
            alt="…">
     We mirror data-resolved-theme on <html>: any change to light/dark theme
     swaps the src attribute. Skips the swap when no dark variant configured. */
  function applyAdaptiveLogos() {
    var resolved = document.documentElement.getAttribute("data-resolved-theme") || "light";
    var imgs = document.querySelectorAll("img.rmc-logo-adaptive-img");
    for (var i = 0; i < imgs.length; i++) {
      var img = imgs[i];
      var dark = img.getAttribute("data-logo-dark-src");
      var light = img.getAttribute("data-logo-light-src") || img.getAttribute("src");
      if (!light && !dark) continue;
      var target = (resolved === "dark" && dark) ? dark : light;
      if (target && img.getAttribute("src") !== target) {
        img.setAttribute("src", target);
      }
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyAdaptiveLogos);
  } else {
    applyAdaptiveLogos();
  }
  /* theme-preference-bootstrap.js dispatches `rmc:theme-change` whenever the
     user-facing toggle changes preference, and updates data-resolved-theme on
     OS theme flips. Observe attribute changes so the system mode is covered. */
  window.addEventListener("rmc:theme-change", applyAdaptiveLogos);
  if (typeof MutationObserver === "function") {
    new MutationObserver(applyAdaptiveLogos).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-resolved-theme"]
    });
  }
})();
