/**
 * Threshold Era marketing — heartbeat, scroll reveals, header shrink.
 */
(function () {
  "use strict";

  var root = document.documentElement;
  if (root.getAttribute("data-mkt-edition") !== "threshold-era") return;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (!document.querySelector(".mkt-th-heartbeat")) {
    var hb = document.createElement("div");
    hb.className = "mkt-th-heartbeat";
    hb.setAttribute("aria-hidden", "true");
    document.body.prepend(hb);
  }

  var header = document.querySelector(".mkt-platform-header, .rmc-platform-header");
  if (header) {
    var onScroll = function () {
      header.classList.toggle("is-scrolled", window.scrollY > 24);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  if (!reduced) {
    var reveals = document.querySelectorAll(".mkt-th-reveal");
    if (reveals.length && "IntersectionObserver" in window) {
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (e) {
            if (e.isIntersecting) {
              e.target.classList.add("is-visible");
              io.unobserve(e.target);
            }
          });
        },
        { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
      );
      reveals.forEach(function (el) {
        io.observe(el);
      });
    } else {
      reveals.forEach(function (el) {
        el.classList.add("is-visible");
      });
    }
  } else {
    document.querySelectorAll(".mkt-th-reveal").forEach(function (el) {
      el.classList.add("is-visible");
    });
  }

  document.querySelectorAll(".mkt-th-door").forEach(function (door) {
    door.addEventListener("click", function () {
      document.querySelectorAll(".mkt-th-door").forEach(function (d) {
        d.classList.remove("is-active");
      });
      door.classList.add("is-active");
    });
  });
})();
