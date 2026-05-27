/**
 * Fluid classroom framework tab morph — emphasize active column in SVG.
 */
(function () {
  "use strict";

  function setFramework(root, framework) {
    var viz = root.querySelector("[data-mkt-gradebook-viz]");
    if (!viz) return;
    viz.querySelectorAll("[data-mkt-framework-column]").forEach(function (col) {
      var active = col.getAttribute("data-mkt-framework-column") === framework;
      col.classList.toggle("is-emphasized", active);
      col.classList.toggle("is-dimmed", !active);
    });
  }

  function init(root) {
    var tabs = root.querySelectorAll("[data-mkt-framework]");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var framework = tab.getAttribute("data-mkt-framework");
        tabs.forEach(function (t) {
          t.classList.remove("is-active");
          t.setAttribute("aria-selected", "false");
        });
        tab.classList.add("is-active");
        tab.setAttribute("aria-selected", "true");
        setFramework(root, framework);
      });
    });
    var active = root.querySelector("[data-mkt-framework].is-active");
    if (active) {
      setFramework(root, active.getAttribute("data-mkt-framework"));
    }
  }

  document.querySelectorAll("[data-mkt-gradebook-morph]").forEach(init);
})();
