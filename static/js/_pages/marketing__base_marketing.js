    (function () {
      var h = document.documentElement;
      var dt = (h.getAttribute("data-theme") || "light").toLowerCase();
      if (dt === "system") {
        var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
        h.setAttribute("data-bs-theme", dark ? "dark" : "light");
      } else {
        h.setAttribute("data-bs-theme", dt === "dark" ? "dark" : "light");
      }
    })();
  
