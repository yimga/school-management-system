/**
 * Sticky section-nav active-state observer.
 *
 * Markup contract (long page authors):
 *   <aside class="rmc-section-nav">
 *     <div class="rmc-section-nav__label">Sections</div>
 *     <ul class="rmc-section-nav__list">
 *       <li><a href="#overview"><i class="bi bi-grid"></i>Overview</a></li>
 *       …
 *     </ul>
 *   </aside>
 *
 *   <section id="overview" data-rmc-section-anchor>…</section>
 *
 * IntersectionObserver toggles `.is-active` on the matching nav link as the
 * user scrolls, and clicking a link scrolls smoothly with offset for sticky chrome.
 */
(function () {
  "use strict";

  function init() {
    var navs = document.querySelectorAll(".rmc-section-nav");
    if (!navs.length) { return; }

    navs.forEach(function (nav) {
      var links = nav.querySelectorAll(".rmc-section-nav__list a[href^='#']");
      if (!links.length) { return; }

      var targets = [];
      links.forEach(function (a) {
        var hash = a.getAttribute("href");
        if (!hash || hash === "#") { return; }
        var el = document.querySelector(hash);
        if (el) {
          targets.push({ el: el, link: a });
        }
        a.addEventListener("click", function (e) {
          var t = document.querySelector(hash);
          if (!t) { return; }
          e.preventDefault();
          var topOffset = 72;
          var rootStyle = getComputedStyle(document.documentElement);
          var chromePx = parseInt(
            rootStyle.getPropertyValue("--rmc-cp-chrome-offset"),
            10
          );
          if (!Number.isNaN(chromePx) && chromePx > 0) {
            topOffset = chromePx + 8;
          }
          var container =
            window.RMC && window.RMC.getScrollContainer
              ? window.RMC.getScrollContainer()
              : null;
          var y = t.getBoundingClientRect().top + (container ? container.scrollTop : window.scrollY) - topOffset;
          if (window.RMC && window.RMC.scrollToY) {
            window.RMC.scrollToY(container, Math.max(0, y), "smooth");
          } else if (container) {
            container.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
          } else {
            window.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
          }
          history.replaceState(null, "", hash);
          markActive(a);
        });
      });

      function markActive(activeLink) {
        links.forEach(function (a) {
          var on = a === activeLink;
          a.classList.toggle("is-active", on);
          a.classList.toggle("active", on);
        });
      }

      if (!("IntersectionObserver" in window) || !targets.length) {
        markActive(links[0]);
        return;
      }

      var io = new IntersectionObserver(function (entries) {
        /* Pick the entry closest to the top that is intersecting. */
        var topMost = null;
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            if (!topMost || entry.boundingClientRect.top < topMost.boundingClientRect.top) {
              topMost = entry;
            }
          }
        });
        if (topMost) {
          var match = targets.find(function (t) { return t.el === topMost.target; });
          if (match) { markActive(match.link); }
        }
      }, { rootMargin: "-64px 0px -55% 0px", threshold: [0, 0.4, 1] });

      targets.forEach(function (t) { io.observe(t.el); });

      /* Initial state based on hash. */
      if (window.location.hash) {
        var first = Array.prototype.find.call(links, function (a) {
          return a.getAttribute("href") === window.location.hash;
        });
        if (first) { markActive(first); }
      } else {
        markActive(links[0]);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
