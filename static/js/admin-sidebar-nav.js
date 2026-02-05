/**
 * Admin sidebar keyboard navigation.
 * Arrow keys: Up/Down to move focus; Enter/Space to activate.
 */
(function () {
  function init() {
    var sidebar = document.getElementById("nav-sidebar");
    if (!sidebar) return;

    var focusables = sidebar.querySelectorAll(
      'a[href], button:not([disabled]), [tabindex="0"]'
    );

    function getIndex(el) {
      var arr = Array.prototype.slice.call(focusables);
      return arr.indexOf(el);
    }

    function handleKeydown(e) {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      var target = e.target;
      if (!sidebar.contains(target)) return;

      var idx = getIndex(target);
      if (idx < 0) return;

      var next = null;
      if (e.key === "ArrowDown" && idx < focusables.length - 1) {
        next = focusables[idx + 1];
      } else if (e.key === "ArrowUp" && idx > 0) {
        next = focusables[idx - 1];
      } else if (e.key === "Home") {
        next = focusables[0];
      } else if (e.key === "End") {
        next = focusables[focusables.length - 1];
      }

      if (next) {
        e.preventDefault();
        next.focus();
      }
    }

    sidebar.addEventListener("keydown", handleKeydown);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
