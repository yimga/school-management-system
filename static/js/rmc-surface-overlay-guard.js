/**
 * Unblocks clicks when Unfold/Bootstrap leave invisible overlays (manager + CP + /admin/).
 * v3.62.20 (2026-05-23)
 */
(function () {
  "use strict";

  function isProtectedSurface() {
    if (!document.body) return false;
    var b = document.body;
    if (
      b.classList.contains("admin-manager-shell") ||
      b.classList.contains("admin-premium-shell") ||
      b.classList.contains("control-plane-shell") ||
      b.getAttribute("data-rmc-admin-cp-unified") === "1" ||
      b.getAttribute("data-rmc-admin-shell") === "1"
    ) {
      return true;
    }
    return (
      b.classList.contains("portal-body-with-layout") &&
      b.getAttribute("data-rmc-premium-shell") === "portal" &&
      !b.classList.contains("marketing-surface")
    );
  }

  function visibleModalOpen() {
    return !!document.querySelector(
      ".modal.show, .modal[style*='display: block'], .offcanvas.show"
    );
  }

  function hideModalOverlay() {
    var mo = document.getElementById("modal-overlay");
    if (!mo) return;
    if (visibleModalOpen()) return;
    mo.classList.add("hidden");
    mo.setAttribute("aria-hidden", "true");
    mo.style.display = "none";
    mo.style.visibility = "hidden";
    mo.style.pointerEvents = "none";
    mo.style.opacity = "0";
  }

  function removeStaleBackdrops() {
    if (visibleModalOpen()) return;
    document
      .querySelectorAll(".modal-backdrop, .offcanvas-backdrop")
      .forEach(function (bd) {
        if (bd && bd.parentNode) bd.remove();
      });
  }

  function unlockAssistBackdrop() {
    document.querySelectorAll(".rmc-assist-dock__backdrop").forEach(function (bd) {
      if (!bd) return;
      var panel = document.body.getAttribute("data-rmc-assist-panel");
      if (panel === "ai" || panel === "feedback") return;
      bd.hidden = true;
      bd.setAttribute("hidden", "");
      bd.style.pointerEvents = "none";
      bd.style.display = "none";
    });
  }

  function purgeFullScreenBlockers() {
    if (visibleModalOpen()) return;
    var vw = window.innerWidth || document.documentElement.clientWidth || 0;
    var vh = window.innerHeight || document.documentElement.clientHeight || 0;
    if (!vw || !vh) return;

    var nodes = document.querySelectorAll("body *");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!el || el.id === "modal-overlay") continue;
      if (el.closest(".modal.show, .offcanvas.show")) continue;
      if (el.closest(".rmc-assist-dock__backdrop:not([hidden])")) continue;
      var st = window.getComputedStyle(el);
      if (st.position !== "fixed" && st.position !== "absolute") continue;
      if (st.pointerEvents === "none" || st.display === "none" || st.visibility === "hidden") {
        continue;
      }
      var op = parseFloat(st.opacity);
      if (!isNaN(op) && op < 0.05) continue;
      var rect = el.getBoundingClientRect();
      if (rect.width < vw * 0.85 || rect.height < vh * 0.85) continue;
      if (rect.top > 8 || rect.left > 8) continue;
      var z = parseInt(st.zIndex, 10);
      if (isNaN(z) || z < 20) continue;
      if (
        el.classList.contains("rmc-app-shell__header") ||
        el.classList.contains("rmc-app-shell__sidebar") ||
        el.classList.contains("rmc-app-shell__canvas") ||
        el.classList.contains("rmc-app-shell__footer")
      ) {
        continue;
      }
      el.style.pointerEvents = "none";
      if (el.classList.contains("modal-backdrop") || el.classList.contains("offcanvas-backdrop")) {
        el.remove();
      }
    }
  }

  function forceShellInteractive() {
    document.documentElement.style.pointerEvents = "";
    document.body.style.pointerEvents = "";
    var canvas = document.querySelector(".rmc-app-shell__canvas, #cp-main-content, #main");
    if (canvas) canvas.style.pointerEvents = "";
  }

  // #region agent log
  var _dbgRuns = 0;
  function _agentDbg(hypothesisId, message, data) {
    _dbgRuns += 1;
    if (_dbgRuns > 40) return;
    fetch("http://127.0.0.1:7426/ingest/383483ef-728e-4a6f-8288-6731caa89dc7", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Debug-Session-Id": "0169af",
      },
      body: JSON.stringify({
        sessionId: "0169af",
        runId: "click-guard",
        hypothesisId: hypothesisId,
        location: "rmc-surface-overlay-guard.js:sanitize",
        message: message,
        data: data || {},
        timestamp: Date.now(),
      }),
    }).catch(function () {});
  }
  // #endregion

  function sanitize() {
    if (!isProtectedSurface()) return;
    var mo = document.getElementById("modal-overlay");
    var moDisplay = mo ? window.getComputedStyle(mo).display : "missing";
    var backdropCount = document.querySelectorAll(
      ".modal-backdrop, .offcanvas-backdrop"
    ).length;
    hideModalOverlay();
    removeStaleBackdrops();
    unlockAssistBackdrop();
    purgeFullScreenBlockers();
    forceShellInteractive();
    // #region agent log
    if (moDisplay !== "none" || backdropCount > 0) {
      _agentDbg("A", "overlay-sanitize", {
        modalOverlayDisplay: moDisplay,
        backdropCount: backdropCount,
        visibleModal: visibleModalOpen(),
        bodyPointerEvents: window.getComputedStyle(document.body).pointerEvents,
      });
    }
    // #endregion
  }

  function isInteractive(el) {
    return (
      el &&
      el.closest &&
      el.closest(
        "a[href], button, input, select, textarea, summary, label, [role='button'], [tabindex]:not([tabindex='-1']), [data-rmc-page-help]"
      )
    );
  }

  function boot() {
    sanitize();
    // #region agent log
    _agentDbg("boot", "overlay-guard-boot", {
      surface: document.body ? document.body.className : "",
      modalOverlay: !!document.getElementById("modal-overlay"),
    });
    // #endregion
    window.setInterval(sanitize, 1500);
    if (typeof MutationObserver === "function") {
      var scheduled = false;
      var obs = new MutationObserver(function () {
        if (scheduled) return;
        scheduled = true;
        window.requestAnimationFrame(function () {
          scheduled = false;
          sanitize();
        });
      });
      obs.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["class", "style", "hidden", "aria-hidden"],
      });
    }
    document.addEventListener(
      "click",
      function (e) {
        if (!isProtectedSurface()) return;
        if (e.defaultPrevented) return;
        var el = isInteractive(e.target);
        if (!el) return;
        var top = document.elementFromPoint(e.clientX, e.clientY);
        if (!top || top === el || el.contains(top)) return;
        // #region agent log
        _agentDbg("C", "click-blocked-by-overlay", {
          intendedTag: el.tagName,
          topTag: top.tagName,
          topId: top.id || "",
          topClass: (top.className && String(top.className).slice(0, 80)) || "",
        });
        // #endregion
        sanitize();
        var topAfter = document.elementFromPoint(e.clientX, e.clientY);
        if (topAfter && (topAfter === el || el.contains(topAfter))) {
          return;
        }
        if (!e._rmcOverlayRetried) {
          e._rmcOverlayRetried = true;
          try {
            el.click();
          } catch (_err) {
            /* swallow */
          }
        }
      },
      true
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
