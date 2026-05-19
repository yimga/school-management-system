/**
 * Operator Help Center — focus search on "?" when not typing in a field.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-rmc-page='help-center']");
  if (!root) {
    return;
  }

  function isTypingTarget(el) {
    if (!el || !el.tagName) {
      return false;
    }
    var tag = el.tagName.toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "?" || ev.ctrlKey || ev.metaKey || ev.altKey) {
      return;
    }
    if (isTypingTarget(ev.target)) {
      return;
    }
    var input = root.querySelector("[data-rmc-help-search-input]");
    if (!input) {
      return;
    }
    ev.preventDefault();
    input.focus();
    input.select();
  });
})();
