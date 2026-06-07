/**
 * Top-of-page progress bar — Apple-style bar for HTMX swaps, cross-document
 * navigations, and arbitrary async work (uploads, fetches, long tasks).
 *
 * v2 (10X): concurrency-aware, determinate-capable, error-visible, with a
 * public programmatic API. Backwards compatible — the DOM contract and the
 * existing auto-bindings (HTMX + left-click nav) are unchanged.
 *
 * DOM contract (mounted once to <body>):
 *   <div class="rmc-page-progress" role="progressbar" aria-hidden="true">
 *     <div class="rmc-page-progress__fill" style="--p: 0%"></div>
 *   </div>
 * Fill driven by the `--p` custom property; `data-state` ∈ idle|loading|done|error.
 * Honors prefers-reduced-motion (no shimmer/comet) + prefers-reduced-transparency.
 *
 * Public API — window.RMCPageProgress:
 *   .start()                 begin (or join) an indeterminate task; ref-counted
 *   .set(pct[, opts])        set fill 0..100; pct≥0 switches to DETERMINATE mode
 *   .inc([amount])           nudge an indeterminate bar forward
 *   .done()                  finish one task; bar completes when all tasks end
 *   .fail([opts])            finish one task with a visible error flash
 *   .configure(opts)         { trackFetch:boolean, trickleMs:number }
 *   .promise(p)              wrap a promise: start → done/fail on settle
 *   .during(asyncFn)         run an async fn bracketed by start/done(+fail)
 *
 * `.set(pct)` makes the bar determinate (no auto-trickle) until the next
 * `.done()`/`.fail()`. Concurrent `.start()` calls ref-count, so overlapping
 * HTMX requests no longer let the first response prematurely complete the bar.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var bar = null;
  var fill = null;
  var pct = 0;
  var ticking = false;
  var doneTimeout = null;
  var active = 0; // ref-count of in-flight tasks
  var determinate = false; // true once .set() drives the value explicitly
  var trickleTimer = null;

  var cfg = {
    trackFetch: false, // opt-in: wrap window.fetch so async calls show progress
    trickleMs: 180, // cadence of the indeterminate climb
  };

  var reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ensureBar() {
    if (bar && bar.isConnected) return bar;
    bar = document.createElement("div");
    bar.className = "rmc-page-progress";
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-hidden", "true");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.style.setProperty("--p", "0%");
    fill = document.createElement("div");
    fill.className = "rmc-page-progress__fill";
    bar.appendChild(fill);
    (document.body || document.documentElement).appendChild(bar);
    return bar;
  }

  function paint() {
    ticking = false;
    var el = ensureBar();
    el.style.setProperty("--p", pct + "%");
    var state = pct >= 100 ? "done" : pct > 0 ? "loading" : "idle";
    el.setAttribute("data-state", state);
    if (determinate) {
      el.setAttribute("aria-valuenow", String(Math.round(pct)));
      el.removeAttribute("aria-hidden");
    } else {
      el.removeAttribute("aria-valuenow");
      el.setAttribute("aria-hidden", "true");
    }
    el.setAttribute("aria-busy", state === "loading" ? "true" : "false");
  }

  function set(target) {
    pct = Math.max(0, Math.min(100, target));
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(paint);
  }

  function startTrickle() {
    if (trickleTimer || determinate) return;
    trickleTimer = setInterval(function () {
      if (determinate) return;
      if (pct < 88) set(pct + (pct < 50 ? 6 : pct < 75 ? 3 : 1));
    }, cfg.trickleMs);
  }

  function stopTrickle() {
    if (trickleTimer) {
      clearInterval(trickleTimer);
      trickleTimer = null;
    }
  }

  /* Begin (or join) an indeterminate task. Ref-counted: N starts need N dones. */
  function start() {
    active += 1;
    if (doneTimeout) {
      clearTimeout(doneTimeout);
      doneTimeout = null;
    }
    var el = ensureBar();
    el.removeAttribute("data-error");
    if (pct === 0 || pct >= 100) {
      determinate = false;
      set(8);
    }
    startTrickle();
  }

  /* Explicit value 0..100 — switches the bar to DETERMINATE mode. */
  function setProgress(target, opts) {
    if (typeof target !== "number" || isNaN(target)) return;
    if (active === 0) active = 1; // a bare .set() implies one task
    determinate = true;
    stopTrickle();
    if (doneTimeout) {
      clearTimeout(doneTimeout);
      doneTimeout = null;
    }
    ensureBar().removeAttribute("data-error");
    if (target >= 100 && !(opts && opts.hold)) {
      complete(false);
    } else {
      set(target);
    }
  }

  /* Nudge an indeterminate bar (no-op while determinate). */
  function inc(amount) {
    if (determinate) return;
    set(pct + (typeof amount === "number" ? amount : 6));
  }

  function complete(isError) {
    stopTrickle();
    active = 0;
    var el = ensureBar();
    if (isError) {
      el.setAttribute("data-error", "1");
      determinate = false;
    }
    set(100);
    var fade = isError ? 620 : 280;
    doneTimeout = setTimeout(function () {
      determinate = false;
      el.removeAttribute("data-error");
      set(0);
    }, fade);
  }

  /* Finish ONE task. The bar completes only when the last task ends. */
  function done() {
    if (active > 0) active -= 1;
    if (active > 0) return; // other tasks still running
    complete(false);
  }

  /* Finish one task with a visible error flash, regardless of remaining count. */
  function fail() {
    complete(true);
  }

  function configure(opts) {
    if (!opts) return;
    if (typeof opts.trickleMs === "number" && opts.trickleMs > 0) {
      cfg.trickleMs = opts.trickleMs;
    }
    if (typeof opts.trackFetch === "boolean") {
      cfg.trackFetch = opts.trackFetch;
      if (cfg.trackFetch) installFetchHook();
    }
  }

  /* Bracket a promise with start → done/fail. Returns the same promise. */
  function wrapPromise(p) {
    if (!p || typeof p.then !== "function") return p;
    start();
    p.then(
      function () { done(); },
      function () { fail(); }
    );
    return p;
  }

  /* Run an async function bracketed by the bar; rethrows so callers can catch. */
  function during(fn) {
    start();
    var out;
    try {
      out = fn();
    } catch (e) {
      fail();
      throw e;
    }
    if (out && typeof out.then === "function") {
      return out.then(
        function (v) { done(); return v; },
        function (e) { fail(); throw e; }
      );
    }
    done();
    return out;
  }

  /* Opt-in: surface every window.fetch as bar activity (ref-counted). */
  var fetchHooked = false;
  function installFetchHook() {
    if (fetchHooked || typeof window.fetch !== "function") return;
    fetchHooked = true;
    var nativeFetch = window.fetch.bind(window);
    window.fetch = function () {
      start();
      var settled = false;
      var finish = function (ok) {
        if (settled) return;
        settled = true;
        ok ? done() : fail();
      };
      try {
        return nativeFetch.apply(null, arguments).then(
          function (r) { finish(true); return r; },
          function (e) { finish(false); throw e; }
        );
      } catch (e) {
        finish(false);
        throw e;
      }
    };
  }

  /* ---- HTMX auto-binding (XHR-based, distinct from fetch) ---- */
  var body = document.body;
  if (body) {
    body.addEventListener("htmx:beforeRequest", start);
    body.addEventListener("htmx:beforeSwap", function () {
      /* beforeSwap fires after the response is in-flight; keep the bar alive
         without double-counting (beforeRequest already incremented). */
      if (active === 0) start();
    });
    body.addEventListener("htmx:afterSettle", done);
    body.addEventListener("htmx:responseError", fail);
    body.addEventListener("htmx:sendError", fail);
    body.addEventListener("htmx:abort", fail);
    body.addEventListener("htmx:timeout", fail);
  }

  /* Cross-document navigation: start on beforeunload for left-clicked
     same-origin links. The bar element persists in the unloading document
     just long enough to feel snappy; the next page mounts a fresh bar. */
  window.addEventListener("beforeunload", function () {
    if (document.documentElement.classList.contains("vt-active")) return;
    /* A full navigation has no matching "done" in this document, so don't
       ref-count it — just show motion until the page is replaced. */
    if (active === 0) {
      active = 1;
      determinate = false;
      set(8);
      startTrickle();
    }
  });

  /* On pageshow (after bfcache restore), reset to idle. */
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
      stopTrickle();
      active = 0;
      determinate = false;
      set(0);
    }
  });

  window.RMCPageProgress = {
    start: start,
    set: setProgress,
    inc: inc,
    done: done,
    fail: fail,
    configure: configure,
    promise: wrapPromise,
    during: during,
  };
})();
