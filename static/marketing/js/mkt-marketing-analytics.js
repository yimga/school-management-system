/*!
 * mkt-marketing-analytics.js — event tracking for the redesigned marketing
 * surface (CTA clicks, product-tour step changes, in-view section reveals).
 *
 * Vanilla / framework-free, no inline handlers, fully CSP-clean (loads as a
 * same-origin `{% static %}` <script src>, so it needs NO nonce under the
 * platform's `script-src 'self'` policy). Every listener is feature-detected
 * and defensive: analytics must never throw into the marketing surface.
 *
 * ── Dispatch contract ──────────────────────────────────────────────────────
 * Each tracked interaction emits ONE normalized payload object to three sinks
 * so any consumer can subscribe without coupling to a specific tag manager:
 *
 *   1. The platform's existing marketing-analytics bus, when present:
 *        - pushes onto `window.rmcMarketingAnalyticsEvents` (array buffer)
 *        - dispatches `CustomEvent("rmc:marketing-analytics", {detail})`
 *      (this is what static/marketing/js/marketing-analytics.js already uses,
 *       including its optional sendBeacon → config.endpoint forwarder).
 *   2. `window.dataLayer` (created if absent) — Google Tag Manager / GA4 style.
 *   3. `CustomEvent("rmc:analytics", {detail})` on `document` — a generic hook
 *      any first- or third-party consumer can `addEventListener` to.
 *
 * Subscribe example:
 *   document.addEventListener("rmc:analytics", function (e) {
 *     console.log(e.detail.event, e.detail);
 *   });
 *
 * ── Events emitted ─────────────────────────────────────────────────────────
 *   cta_click    { event, cta, page, label, href, ts }
 *   tour_step    { event, tour, step, total, direction, ts }
 *   section_view { event, section, label, ts }   (once per section, per load)
 */
(function () {
  "use strict";

  if (typeof document === "undefined" || !document.addEventListener) {
    return;
  }

  function now() {
    try {
      return new Date().toISOString();
    } catch (err) {
      return "";
    }
  }

  // GDPR: only the in-page rmc:analytics CustomEvent (no network) fires before
  // consent. The network-capable sinks (the marketing-analytics bus, which can
  // sendBeacon, and window.dataLayer/GTM) are gated on explicit analytics
  // consent. Privacy-safe default: if no consent mechanism has resolved a
  // choice yet, treat analytics as NOT granted.
  function analyticsConsentGranted() {
    try {
      if (window.rmcConsent && typeof window.rmcConsent.granted === "function") {
        return !!window.rmcConsent.granted("analytics");
      }
    } catch (err) {
      /* consent layer unavailable — fall through to deny */
    }
    return false;
  }

  function pageSlug() {
    var el = document.documentElement;
    var ds = (el && el.dataset) || {};
    return (
      ds.rmcPageSlug ||
      ds.mktPersonality ||
      (window.location && window.location.pathname) ||
      "unknown"
    );
  }

  // ── Dispatch to all three sinks. Each sink is independently guarded so a
  //    failure in one never starves the others or bubbles into the page. ──
  function emit(detail) {
    if (!detail || typeof detail !== "object") {
      return;
    }
    if (!detail.ts) {
      detail.ts = now();
    }

    var allowed = analyticsConsentGranted();

    // Sink 1: existing platform marketing-analytics bus (best-effort).
    // GATED: this bus can sendBeacon to an endpoint, so it only runs with
    // analytics consent.
    if (allowed) {
      try {
        window.rmcMarketingAnalyticsEvents = window.rmcMarketingAnalyticsEvents || [];
        window.rmcMarketingAnalyticsEvents.push(detail);
        window.dispatchEvent(
          new CustomEvent("rmc:marketing-analytics", { detail: detail })
        );
      } catch (err) {
        /* bus unavailable — fall through to the generic sinks */
      }

      // Sink 2: dataLayer (GTM/GA4 convention). Create if absent. GATED.
      try {
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push(detail);
      } catch (err) {
        /* dataLayer push failed — non-fatal */
      }
    }

    // Sink 3: generic document-level CustomEvent for any subscriber. This is
    // in-page only (no network), so it always fires — lets first-party code
    // react without tracking the user externally. Shape unchanged (the payload
    // itself); a non-enumerable-ish consent hint is attached for subscribers
    // that care, without disturbing the documented event fields.
    try {
      detail.consentGranted = allowed;
      document.dispatchEvent(new CustomEvent("rmc:analytics", { detail: detail }));
    } catch (err) {
      /* CustomEvent unsupported — non-fatal */
    }
  }

  function textOf(el) {
    if (!el) {
      return "";
    }
    var raw = el.getAttribute("aria-label") || el.textContent || "";
    return raw.replace(/\s+/g, " ").trim().slice(0, 120);
  }

  function closest(el, selector) {
    return el && el.closest ? el.closest(selector) : null;
  }

  // ── 1. CTA clicks (event delegation on document) ──────────────────────────
  document.addEventListener("click", function (ev) {
    var target = ev.target;
    if (!target) {
      return;
    }

    var cta = closest(target, "[data-cta]");
    if (cta) {
      emit({
        event: "cta_click",
        cta: cta.getAttribute("data-cta") || "",
        page: cta.getAttribute("data-page") || pageSlug(),
        label: cta.getAttribute("data-cta-label") || textOf(cta),
        href: cta.getAttribute("href") || ""
      });
      return;
    }

    // ── 2. Product-tour step changes (next / prev / dot) ───────────────────
    var tourControl = closest(
      target,
      "[data-mkt-tour-next], [data-mkt-tour-prev], [data-mkt-tour-dot]"
    );
    if (tourControl) {
      var root = closest(tourControl, "[data-mkt-tour]");
      var slug = (root && root.getAttribute("data-mkt-tour-slug")) || "";
      var frames = root
        ? root.querySelectorAll("[data-mkt-tour-frame]")
        : null;
      var total = frames ? frames.length : 0;

      var direction = "jump";
      var step = null;

      if (tourControl.hasAttribute("data-mkt-tour-next")) {
        direction = "next";
      } else if (tourControl.hasAttribute("data-mkt-tour-prev")) {
        direction = "prev";
      } else if (tourControl.hasAttribute("data-mkt-tour-dot")) {
        direction = "jump";
        // Resolve the dot's 1-based index among its sibling dots.
        if (root) {
          var dots = Array.prototype.slice.call(
            root.querySelectorAll("[data-mkt-tour-dot]")
          );
          var idx = dots.indexOf(tourControl);
          if (idx >= 0) {
            step = idx + 1;
          }
        }
      }

      emit({
        event: "tour_step",
        tour: slug,
        step: step,
        total: total,
        direction: direction
      });
    }
  });

  // ── 3. Section visibility (once per section, per page load) ───────────────
  function observeSections() {
    var selector =
      "[data-mkt-personality-viz], .mkt-rails, .mkt-outcome-band";
    var nodes;
    try {
      nodes = document.querySelectorAll(selector);
    } catch (err) {
      return;
    }
    if (!nodes || !nodes.length) {
      return;
    }

    function sectionName(el) {
      if (el.hasAttribute("data-mkt-personality-viz")) {
        return el.getAttribute("data-mkt-personality-viz") || "personality_viz";
      }
      if (el.classList) {
        if (el.classList.contains("mkt-rails")) {
          return (
            "rails:" +
            (el.getAttribute("data-mkt-rails-kind") || "default")
          );
        }
        if (el.classList.contains("mkt-outcome-band")) {
          return "outcome_band";
        }
      }
      return "section";
    }

    // No IntersectionObserver → emit a single best-effort view per section now
    // so the events are not silently lost on legacy browsers.
    if (typeof window.IntersectionObserver !== "function") {
      Array.prototype.forEach.call(nodes, function (el) {
        if (el.__mktViewFired) {
          return;
        }
        el.__mktViewFired = true;
        emit({
          event: "section_view",
          section: sectionName(el),
          label: el.getAttribute("aria-label") || ""
        });
      });
      return;
    }

    try {
      var io = new window.IntersectionObserver(
        function (entries, observer) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) {
              return;
            }
            var el = entry.target;
            if (el.__mktViewFired) {
              observer.unobserve(el);
              return;
            }
            el.__mktViewFired = true;
            observer.unobserve(el);
            emit({
              event: "section_view",
              section: sectionName(el),
              label: el.getAttribute("aria-label") || ""
            });
          });
        },
        { threshold: 0.35 }
      );
      Array.prototype.forEach.call(nodes, function (el) {
        io.observe(el);
      });
    } catch (err) {
      /* IO constructor unsupported — graceful no-op. */
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", observeSections);
  } else {
    observeSections();
  }
})();
