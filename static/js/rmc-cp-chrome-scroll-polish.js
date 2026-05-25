/**
 * Scroll-linked chrome polish: frosted sticky header, progress bar, sidebar fades.
 */
(function () {
  "use strict";

  var ticking = false;

  function sidebarNodes() {
    return document.querySelectorAll(
      ".cp-sidebar-inner, #cp-sidebar-col .cp-sidebar-inner, #nav-sidebar-apps, .admin-sidebar-apps, .portal-sidebar-col .sidebar, #portal-sidebar-col .sidebar"
    );
  }

  function scrollContainerFor(el) {
    if (!el) return null;
    return (
      el.closest(
        ".cp-sidebar-inner, #nav-sidebar-apps, .admin-sidebar-apps, .portal-sidebar-col .sidebar, #portal-sidebar-col .sidebar"
      ) || null
    );
  }

  function ensureDisclosureVisible(target) {
    var container = scrollContainerFor(target);
    if (!container) return;
    requestAnimationFrame(function () {
      var targetRect = target.getBoundingClientRect();
      var containerRect = container.getBoundingClientRect();
      if (targetRect.bottom > containerRect.bottom - 4) {
        container.scrollTop += targetRect.bottom - containerRect.bottom + 12;
      } else if (targetRect.top < containerRect.top + 4) {
        container.scrollTop -= containerRect.top - targetRect.top + 12;
      }
      updateSidebarFades(container);
    });
  }

  function bindDisclosureToggles(root) {
    var scope = root || document;
    scope.querySelectorAll(".cp-sidebar-inner details, #nav-sidebar-apps details").forEach(function (detailsEl) {
      if (detailsEl.getAttribute("data-rmc-disclosure-bound")) return;
      detailsEl.setAttribute("data-rmc-disclosure-bound", "1");
      detailsEl.addEventListener("toggle", function () {
        if (detailsEl.open) {
          ensureDisclosureVisible(detailsEl);
        }
        sidebarNodes().forEach(updateSidebarFades);
      });
    });
    scope.querySelectorAll("#nav-sidebar-apps .admin-sidebar-app-toggle, #nav-sidebar .admin-sidebar-app-toggle").forEach(function (btn) {
      if (btn.getAttribute("data-rmc-disclosure-bound")) return;
      btn.setAttribute("data-rmc-disclosure-bound", "1");
      btn.addEventListener("click", function () {
        var group = btn.closest(".admin-sidebar-app-group");
        if (group) {
          window.requestAnimationFrame(function () {
            ensureDisclosureVisible(group);
          });
        }
      });
    });
    scope.querySelectorAll("#nav-sidebar-apps .admin-sidebar-all-apps-trigger").forEach(function (btn) {
      if (btn.getAttribute("data-rmc-disclosure-bound")) return;
      btn.setAttribute("data-rmc-disclosure-bound", "1");
      btn.addEventListener("click", function () {
        var block = btn.closest(".admin-sidebar-all-apps");
        if (block) {
          window.requestAnimationFrame(function () {
            ensureDisclosureVisible(block);
          });
        }
      });
    });
  }

  function updateSidebarFades(el) {
    if (!el) return;
    var max = el.scrollHeight - el.clientHeight;
    if (max < 8) {
      el.removeAttribute("data-rmc-sidebar-scrollable");
      el.style.setProperty("--rmc-sidebar-fade-top", "0");
      el.style.setProperty("--rmc-sidebar-fade-bottom", "0");
      return;
    }
    el.setAttribute("data-rmc-sidebar-scrollable", "1");
    var top = el.scrollTop;
    el.style.setProperty("--rmc-sidebar-fade-top", top > 6 ? "1" : "0");
    el.style.setProperty(
      "--rmc-sidebar-fade-bottom",
      top < max - 6 ? "1" : "0"
    );
  }

  function updateNotifyPulse() {
    var badge = document.querySelector(".cp-topbar-bell__badge");
    if (!badge || !document.body) return;
    var n = parseInt((badge.textContent || "").trim(), 10);
    if (!Number.isNaN(n) && n > 0) {
      document.body.setAttribute("data-rmc-cp-notify-pulse", "1");
    } else {
      document.body.removeAttribute("data-rmc-cp-notify-pulse");
    }
  }

  function measure() {
    var doc = document.documentElement;
    var y = window.scrollY || doc.scrollTop || 0;
    var max = Math.max(1, (doc.scrollHeight || 0) - window.innerHeight);
    var progress = Math.min(1, Math.max(0, y / max));

    doc.style.setProperty("--rmc-doc-scroll-progress", String(progress));
    if (document.body) {
      document.body.setAttribute(
        "data-rmc-cp-chrome-scrolled",
        y > 6 ? "1" : "0"
      );
    }

    sidebarNodes().forEach(updateSidebarFades);
    updateNotifyPulse();
  }

  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      ticking = false;
      measure();
    });
  }

  function bindSidebarScroll() {
    sidebarNodes().forEach(function (el) {
      if (el.getAttribute("data-rmc-sidebar-scroll-bound")) return;
      el.setAttribute("data-rmc-sidebar-scroll-bound", "1");
      el.addEventListener("scroll", onScroll, { passive: true });
    });
    bindDisclosureToggles(document);
  }

  function init() {
    if (window.RMC && typeof window.RMC.measureCpChromeOffset === "function") {
      window.RMC.measureCpChromeOffset();
    }
    bindSidebarScroll();
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    if (typeof ResizeObserver !== "undefined") {
      var ro = new ResizeObserver(function () {
        bindSidebarScroll();
        measure();
      });
      sidebarNodes().forEach(function (node) {
        ro.observe(node);
      });
      var chrome = document.querySelector(
        '[data-rmc-control-plane-chrome="1"], .rmc-control-plane-chrome, #portalHeader'
      );
      if (chrome) ro.observe(chrome);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.RMC = window.RMC || {};
  window.RMC.refreshCpChromeScrollPolish = function () {
    bindSidebarScroll();
    measure();
  };
})();
