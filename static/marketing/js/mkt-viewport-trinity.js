/**
 * Viewport trinity — cycle phone / chromebook / NOC + RTL mirror toggle.
 */
(function () {
  "use strict";

  function init(root) {
    var tabs = root.querySelectorAll("[data-mkt-trinity-mode]");
    var panels = root.querySelectorAll("[data-mkt-trinity-panel]");
    var dirBtns = root.querySelectorAll("[data-mkt-trinity-dir]");
    var mirror = root.querySelector(".mkt-ve-trinity__mirror");
    var cycleTimer;

    function show(mode) {
      tabs.forEach(function (tab) {
        var on = tab.getAttribute("data-mkt-trinity-mode") === mode;
        tab.classList.toggle("is-active", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.forEach(function (panel) {
        var on = panel.getAttribute("data-mkt-trinity-panel") === mode;
        panel.hidden = !on;
        panel.classList.toggle("is-active", on);
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        show(tab.getAttribute("data-mkt-trinity-mode") || "phone");
      });
    });

    dirBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        dirBtns.forEach(function (b) {
          b.classList.remove("is-active");
          b.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("is-active");
        btn.setAttribute("aria-pressed", "true");
        if (mirror) mirror.setAttribute("dir", btn.getAttribute("data-mkt-trinity-dir") || "ltr");
      });
    });

    var modes = ["phone", "chromebook", "noc"];
    var idx = 0;
    function cycle() {
      idx = (idx + 1) % modes.length;
      show(modes[idx]);
    }

    cycleTimer = setInterval(cycle, 8000);
    root.addEventListener("mouseenter", function () {
      clearInterval(cycleTimer);
    });
    root.addEventListener("mouseleave", function () {
      cycleTimer = setInterval(cycle, 8000);
    });

    show("phone");
  }

  document.querySelectorAll("[data-mkt-viewport-trinity]").forEach(init);
})();
