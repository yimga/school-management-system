/**
 * rmc-admin-workspace.js (v4.02.12)
 * Builds the manager change-form "On this page" rail nav from the rendered
 * fieldsets + inline groups, with scroll-spy. Purely additive: if the rail or
 * sections are absent it no-ops and leaves the form untouched.
 */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function sectionLabel(sec, index) {
    var h = sec.querySelector(
      ":scope > h2, :scope > details > summary, :scope > .inline-heading, :scope > h3"
    );
    if (!h) h = sec.querySelector("h2, h3, summary");
    var label = h ? (h.textContent || "").replace(/\s+/g, " ").trim() : "";
    if (!label) label = index === 0 ? "General" : "Section " + (index + 1);
    return label.length > 42 ? label.slice(0, 41) + "…" : label;
  }

  ready(function () {
    var nav = document.querySelector("[data-rmc-onthispage]");
    var main = document.getElementById("content-main");
    if (!nav || !main) return;

    var sections = main.querySelectorAll("fieldset.module, .inline-group");
    var items = [];

    Array.prototype.forEach.call(sections, function (sec, i) {
      // Skip hidden/empty fieldsets (e.g. all-hidden-field rows).
      if (sec.offsetParent === null && sec.getClientRects().length === 0) return;
      var label = sectionLabel(sec, items.length);
      if (!sec.id) sec.id = "rmc-sec-" + (i + 1);
      sec.style.scrollMarginTop = "84px";

      var a = document.createElement("a");
      a.href = "#" + sec.id;
      var num = document.createElement("span");
      num.className = "num";
      num.textContent = String(items.length + 1);
      var lbl = document.createElement("span");
      lbl.className = "lbl";
      lbl.textContent = label;
      a.appendChild(num);
      a.appendChild(lbl);
      nav.appendChild(a);
      items.push({ a: a, sec: sec });
    });

    if (!items.length) {
      var card = nav.closest(".rmc-rail-card");
      if (card) card.style.display = "none";
      return;
    }

    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (e) {
            if (e.isIntersecting) {
              items.forEach(function (it) {
                it.a.classList.toggle("is-active", it.sec === e.target);
              });
            }
          });
        },
        { rootMargin: "-35% 0px -55% 0px" }
      );
      items.forEach(function (it) {
        io.observe(it.sec);
      });
    }
  });
})();
