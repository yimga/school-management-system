/**
 * Activation-checklist slide-over (Admin Home cockpit item B).
 *
 * Progressive enhancement over the "Open full activation checklist" link: when the
 * browser supports <dialog> + fetch, a click opens the checklist in an rmc-sheet
 * side drawer (native showModal → focus-trap + Esc-close + focus-return for free)
 * and lazy-loads the chrome-less fragment from siteconfig:onboarding_fragment. With
 * no JS, an unsupported browser, or a fetch failure, the link's href navigates to the
 * full checklist page — the surface is never worse than before.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  function dialogSupported() {
    return (
      typeof window.HTMLDialogElement !== "undefined" &&
      typeof window.HTMLDialogElement.prototype.showModal === "function"
    );
  }

  function loadFragment(sheet, src, trigger) {
    var body = sheet.querySelector("[data-rmc-checklist-body='1']");
    if (!body || sheet.__rmcChecklistLoaded) return;
    fetch(src, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch", Accept: "text/html" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("checklist_http_" + res.status);
        return res.text();
      })
      .then(function (html) {
        // Same-origin, login-gated, auto-escaped server fragment (HTMX-style swap).
        body.innerHTML = html;
        sheet.__rmcChecklistLoaded = true;
        var focusTarget = body.querySelector(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusTarget && typeof focusTarget.focus === "function") {
          try {
            focusTarget.focus({ preventScroll: true });
          } catch (e) {
            /* focus is best-effort */
          }
        }
      })
      .catch(function () {
        // Hard fallback: close the drawer and navigate to the full checklist page.
        var loading = body.querySelector("[data-rmc-checklist-loading='1']");
        if (loading && loading.getAttribute("data-error")) {
          loading.textContent = loading.getAttribute("data-error");
        }
        var href = trigger && trigger.getAttribute("href");
        if (href) window.location.assign(href);
      });
  }

  function wire(trigger) {
    if (trigger.__rmcChecklistWired) return;
    trigger.__rmcChecklistWired = true;
    var sheetId = trigger.getAttribute("aria-controls");
    var src = trigger.getAttribute("data-rmc-checklist-src");
    trigger.addEventListener("click", function (e) {
      // New-tab / modified / middle clicks → let the browser follow the link.
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) return;
      // Capability missing → fall through to normal navigation.
      if (!dialogSupported() || !window.RMCSheet || typeof window.fetch !== "function") {
        return;
      }
      var sheet = sheetId && document.getElementById(sheetId);
      if (!sheet) return;
      e.preventDefault();
      window.RMCSheet.open(sheet);
      if (src) loadFragment(sheet, src, trigger);
    });
  }

  function init() {
    var triggers = document.querySelectorAll("[data-rmc-checklist-drawer='1']");
    Array.prototype.forEach.call(triggers, wire);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
