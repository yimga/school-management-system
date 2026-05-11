/**
 * Marketing motion — Apple-tier microinteractions for the editorial surface.
 *
 *   - Scroll reveal:   IntersectionObserver fades + lifts any element marked
 *                      [data-mkt-reveal] into place when it enters the viewport.
 *                      Honors prefers-reduced-motion.
 *   - Hero parallax:   gentle translateY on [data-mkt-parallax] as the user
 *                      scrolls past the hero. Uses transform only so it stays
 *                      GPU-cheap and never triggers layout.
 *   - Lens keyboard:   arrow keys cycle the radio-driven lens tabs.
 *   - Lazy-init:       no work happens until the user actually scrolls or
 *                      tabs in. No layout thrash on first paint.
 *
 * Loaded as a regular <script defer> from base_marketing.html. ~3 KB, no deps.
 */
(function () {
  "use strict";

  const reduce =
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ───────── 1. Scroll reveal ─────────
  function initReveal() {
    const targets = document.querySelectorAll("[data-mkt-reveal]");
    const staggers = document.querySelectorAll("[data-mkt-reveal-stagger]");
    const all = [...targets, ...staggers];
    if (!all.length) return;

    if (reduce || !("IntersectionObserver" in window)) {
      // Reveal everything immediately; respects users who opt out.
      all.forEach((el) => el.classList.add("is-revealed"));
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-revealed");
          io.unobserve(entry.target);
        });
      },
      // Generous trigger — fires as soon as any pixel enters the viewport,
      // with a 60px lead so the animation runs *before* the element is on
      // screen rather than after.
      { threshold: 0, rootMargin: "0px 0px 60px 0px" },
    );

    all.forEach((el) => io.observe(el));

    // Safety fallback — anything still hidden after 2.5s gets revealed.
    // Covers screenshot tooling, headless browsers, very-fast scrollers,
    // and any edge case where the IO didn't fire.
    setTimeout(() => {
      all.forEach((el) => {
        if (!el.classList.contains("is-revealed")) {
          el.classList.add("is-revealed");
        }
      });
    }, 2500);
  }

  // ───────── 2. Hero parallax ─────────
  function initParallax() {
    if (reduce) return;
    const targets = document.querySelectorAll("[data-mkt-parallax]");
    if (!targets.length) return;

    let ticking = false;
    const apply = () => {
      const y = window.scrollY;
      targets.forEach((el) => {
        const strength = parseFloat(el.dataset.mktParallax || "0.08");
        // Translate by a fraction of scroll, capped so it never feels jarring.
        const shift = Math.max(-40, Math.min(40, -y * strength));
        el.style.transform = `translate3d(0, ${shift}px, 0)`;
      });
      ticking = false;
    };

    window.addEventListener(
      "scroll",
      () => {
        if (ticking) return;
        window.requestAnimationFrame(apply);
        ticking = true;
      },
      { passive: true },
    );
    apply();
  }

  // ───────── 3. Lens tabs — keyboard nav ─────────
  function initLensKeyboard() {
    const tabs = Array.from(
      document.querySelectorAll(".mkt-edt-lens__tabs .mkt-edt-lens__tab"),
    );
    if (!tabs.length) return;

    tabs.forEach((tab, idx) => {
      tab.setAttribute("tabindex", "0");
      tab.setAttribute("role", "tab");

      tab.addEventListener("keydown", (e) => {
        const key = e.key;
        if (
          key !== "ArrowRight" &&
          key !== "ArrowLeft" &&
          key !== "Home" &&
          key !== "End"
        ) {
          return;
        }
        e.preventDefault();
        let next = idx;
        if (key === "ArrowRight") next = (idx + 1) % tabs.length;
        else if (key === "ArrowLeft")
          next = (idx - 1 + tabs.length) % tabs.length;
        else if (key === "Home") next = 0;
        else if (key === "End") next = tabs.length - 1;

        const targetTab = tabs[next];
        const radioId = targetTab.getAttribute("for");
        const radio = radioId && document.getElementById(radioId);
        if (radio) {
          radio.checked = true;
          radio.dispatchEvent(new Event("change", { bubbles: true }));
        }
        targetTab.focus();
      });
    });
  }

  // ───────── 4. Honest pulse + tactile-press for any [data-mkt-tactile] ─────────
  function initTactile() {
    if (reduce) return;
    const targets = document.querySelectorAll("[data-mkt-tactile]");
    targets.forEach((el) => {
      el.addEventListener(
        "pointerdown",
        () => el.classList.add("is-pressed"),
        { passive: true },
      );
      const release = () => el.classList.remove("is-pressed");
      el.addEventListener("pointerup", release, { passive: true });
      el.addEventListener("pointerleave", release, { passive: true });
      el.addEventListener("pointercancel", release, { passive: true });
    });
  }

  // ───────── 5. Live status pill — polls /healthz/ ─────────
  function initStatus() {
    const pill = document.querySelector("[data-mkt-status]");
    if (!pill) return;
    const labelEl = pill.querySelector("[data-mkt-status-label]");
    const setState = (state, label) => {
      pill.setAttribute("data-state", state);
      if (labelEl && label) labelEl.textContent = label;
    };
    const ping = () => {
      // /healthz/ is a fast public endpoint; 200/403 both mean "service up
      // enough to respond". Anything else = degraded/down.
      fetch("/healthz/", {
        method: "GET",
        credentials: "omit",
        cache: "no-store",
        headers: { Accept: "text/plain, application/json" },
      })
        .then((r) => {
          if (r.status >= 200 && r.status < 500) {
            setState("ok", "All systems operational");
          } else if (r.status >= 500) {
            setState("degraded", "Some systems degraded");
          } else {
            setState("unknown", "Status");
          }
        })
        .catch(() => setState("unknown", "Status"));
    };
    ping();
    // Refresh every 60s — quiet, no spammy polling.
    setInterval(ping, 60000);
  }

  function init() {
    // Mark the document as motion-ready so the CSS hidden state actually
    // applies. Without this flag, all [data-mkt-reveal] elements remain
    // visible — progressive enhancement, not progressive frustration.
    document.documentElement.setAttribute("data-mkt-motion-ready", "");
    initReveal();
    initParallax();
    initLensKeyboard();
    initTactile();
    initStatus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
