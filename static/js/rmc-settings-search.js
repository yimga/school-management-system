/**
 * Settings hub: client-side filter as the user types in the rail search,
 * and active-rail-link sync as the user scrolls between category sections.
 */
(function () {
  "use strict";

  function resolveScrollRoot() {
    var canvas = document.getElementById("main-content");
    if (canvas && document.body && document.body.getAttribute("data-rmc-cp-scroll") === "canvas") {
      var oy = window.getComputedStyle(canvas).overflowY;
      if (oy === "auto" || oy === "scroll" || oy === "overlay") {
        return canvas;
      }
    }
    return null;
  }

  function init() {
    var input = document.querySelector(".rmc-settings-search input[name='q']");
    var entries = Array.prototype.slice.call(document.querySelectorAll(".rmc-settings-entry"));
    var sections = Array.prototype.slice.call(document.querySelectorAll(".rmc-settings-section"));
    var railLinks = Array.prototype.slice.call(document.querySelectorAll(".rmc-settings-rail__item"));
    var scrollRoot = resolveScrollRoot();

    function filter(q) {
      var query = (q || "").trim().toLowerCase();
      entries.forEach(function (e) {
        var text = (e.getAttribute("data-rmc-search-text") || "").toLowerCase();
        var match = !query || text.indexOf(query) !== -1;
        e.classList.toggle("is-hidden", !match);
      });
      sections.forEach(function (s) {
        var anyVisible = s.querySelector(".rmc-settings-entry:not(.is-hidden)");
        s.style.display = anyVisible ? "" : "none";
      });
    }

    if (input) {
      input.addEventListener("input", function (e) { filter(e.target.value); });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { input.value = ""; filter(""); }
      });
    }

    /* Rail active state on scroll. */
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        var top = null;
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            if (!top || entry.boundingClientRect.top < top.boundingClientRect.top) { top = entry; }
          }
        });
        if (!top) { return; }
        var slug = top.target.getAttribute("data-rmc-cat");
        railLinks.forEach(function (a) {
          a.classList.toggle("is-active", a.getAttribute("data-rmc-settings-cat") === slug);
        });
      }, {
        root: scrollRoot,
        rootMargin: "-80px 0px -55% 0px",
        threshold: [0, 0.3, 1],
      });
      sections.forEach(function (s) { io.observe(s); });
    }

    /* Smooth-scroll on rail click with offset. */
    railLinks.forEach(function (a) {
      a.addEventListener("click", function (e) {
        var hash = a.getAttribute("href");
        if (!hash || hash.charAt(0) !== "#") { return; }
        var target = document.querySelector(hash);
        if (!target) { return; }
        e.preventDefault();
        if (scrollRoot) {
          var offset = target.getBoundingClientRect().top - scrollRoot.getBoundingClientRect().top + scrollRoot.scrollTop - 72;
          scrollRoot.scrollTo({ top: offset, behavior: "smooth" });
        } else {
          var y = target.getBoundingClientRect().top + window.scrollY - 72;
          window.scrollTo({ top: y, behavior: "smooth" });
        }
        history.replaceState(null, "", hash);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
