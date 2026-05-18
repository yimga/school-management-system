    (function () {
      // v3 contract (2026-05-18): data-theme is always the effective theme
      // ("light"|"dark"), never "system". See docs/THEME_SYSTEM.md §0.
      var h = document.documentElement;
      var dt = (h.getAttribute("data-theme") || "light").toLowerCase();
      h.setAttribute("data-bs-theme", dt === "dark" ? "dark" : "light");
    })();
  
