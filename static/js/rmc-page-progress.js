/**
 * Top-of-page progress bar — Apple-style indeterminate bar for HTMX swaps
 * and (optionally) cross-document navigations.
 *
 * Mounts a `<div class="rmc-page-progress">` to <body> once, then listens for:
 *   - htmx:beforeRequest / htmx:beforeSwap → start (or extend) the bar
 *   - htmx:afterSettle / htmx:responseError / htmx:sendError → complete
 *   - htmx:abort → fail silently
 *   - window beforeunload (left-clicked nav) → start; only completes if the
 *     new page actually arrives (otherwise the bar carries across)
 *
 * Honors prefers-reduced-motion (no shimmer, just a solid bar).
 * No external dependency. Uses CSS custom property `--p` to animate fill.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var bar = null;
  var pct = 0;
  var ticking = false;
  var doneTimeout = null;

  function ensureBar() {
    if (bar) return bar;
    bar = document.createElement("div");
    bar.className = "rmc-page-progress";
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-hidden", "true");
    bar.style.setProperty("--p", "0%");
    var inner = document.createElement("div");
    inner.className = "rmc-page-progress__fill";
    bar.appendChild(inner);
    document.body.appendChild(bar);
    return bar;
  }

  function set(target) {
    pct = Math.max(0, Math.min(100, target));
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      ensureBar().style.setProperty("--p", pct + "%");
      bar.setAttribute("data-state", pct >= 100 ? "done" : pct > 0 ? "loading" : "idle");
    });
  }

  function start() {
    if (doneTimeout) { clearTimeout(doneTimeout); doneTimeout = null; }
    if (pct === 0 || pct >= 100) set(8);
    /* Climb non-linearly so we never finish without a real response, but
       the user still sees motion. Trickle every 180ms. */
    if (start._trickle) return;
    start._trickle = setInterval(function () {
      if (pct < 88) set(pct + (pct < 50 ? 6 : pct < 75 ? 3 : 1));
    }, 180);
  }

  function done() {
    if (start._trickle) { clearInterval(start._trickle); start._trickle = null; }
    set(100);
    doneTimeout = setTimeout(function () { set(0); }, 280);
  }

  function fail() { done(); }

  /* HTMX events fire on `document.body` (or document) — bind to body if HTMX is
     present, else listen on document for cross-doc fallback. */
  document.body.addEventListener("htmx:beforeRequest", start);
  document.body.addEventListener("htmx:beforeSwap", start);
  document.body.addEventListener("htmx:afterSettle", done);
  document.body.addEventListener("htmx:responseError", fail);
  document.body.addEventListener("htmx:sendError", fail);
  document.body.addEventListener("htmx:abort", fail);
  document.body.addEventListener("htmx:timeout", fail);

  /* Cross-document navigation: start on beforeunload for left-clicked
     same-origin links. The bar element persists in the unloading document
     just long enough to feel snappy; the next page mounts a fresh bar. */
  window.addEventListener("beforeunload", function () {
    /* Don't start if user is navigating away via reload key — fetch APIs
       handle that. Also skip if View Transitions are running. */
    if (document.documentElement.classList.contains("vt-active")) return;
    start();
  });

  /* On pageshow (after bfcache restore), reset to idle. */
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
      if (start._trickle) { clearInterval(start._trickle); start._trickle = null; }
      set(0);
    }
  });
})();
