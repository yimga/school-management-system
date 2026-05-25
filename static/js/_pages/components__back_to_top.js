(function () {
  var fold =
    window.RMC && window.RMC.getFoldHeight
      ? window.RMC.getFoldHeight()
      : Math.max(window.innerHeight || 0, 320);
  var scrollThreshold = fold * 2;
  var btn = document.getElementById("back-to-top-btn");
  if (!btn || btn.getAttribute("data-rmc-mounted") === "1") return;
  btn.setAttribute("data-rmc-mounted", "1");

  function getScrollContainer() {
    return window.RMC && window.RMC.getScrollContainer
      ? window.RMC.getScrollContainer()
      : null;
  }

  function getScrollTop(container) {
    return window.RMC && window.RMC.getScrollTop
      ? window.RMC.getScrollTop(container)
      : container
        ? container.scrollTop
        : window.scrollY || document.documentElement.scrollTop;
  }

  function scrollToTop() {
    var container = getScrollContainer();
    if (window.RMC && window.RMC.scrollToY) {
      window.RMC.scrollToY(container, 0, "smooth");
    } else if (container) {
      container.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function updateVisibility() {
    var container = getScrollContainer();
    var top = getScrollTop(container);
    if (top >= scrollThreshold) {
      btn.removeAttribute("hidden");
    } else {
      btn.setAttribute("hidden", "");
    }
  }

  var container = getScrollContainer();
  if (container) {
    container.addEventListener("scroll", updateVisibility, { passive: true });
  }
  window.addEventListener("scroll", updateVisibility, { passive: true });
  btn.addEventListener("click", scrollToTop);
  updateVisibility();
})();
