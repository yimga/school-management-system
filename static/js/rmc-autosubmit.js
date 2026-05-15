/**
 * One-click filter forms. Marks decorated with [data-rmc-autosubmit] auto-
 * submit when any field changes (debounced for text/number inputs), letting
 * users change a class/date picker without also hunting for a Load button.
 *
 * Markup contract:
 *   <form method="get" data-rmc-autosubmit="1">
 *     <select name="..." ...>
 *     <input type="date" name="...">
 *     <!-- Optional: keep the submit button visible as a fallback for
 *          keyboard / no-JS users. Hidden when JS is active via the
 *          [data-rmc-autosubmit-hide-when-js] attribute. -->
 *     <button type="submit" data-rmc-autosubmit-hide-when-js>Load</button>
 *   </form>
 *
 * Honors reduced-motion: the form submits synchronously with no animation.
 * Text inputs are debounced 350ms; selects/dates submit immediately.
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 350;

  function isInstantField(el) {
    if (!el || !el.tagName) { return false; }
    var t = (el.type || "").toLowerCase();
    if (el.tagName === "SELECT") { return true; }
    if (t === "date" || t === "datetime-local" || t === "month" || t === "week" || t === "time") { return true; }
    if (t === "checkbox" || t === "radio") { return true; }
    return false;
  }

  function init() {
    var forms = document.querySelectorAll("form[data-rmc-autosubmit]");
    forms.forEach(function (form) {
      // Hide submit button(s) flagged as JS-redundant.
      form.querySelectorAll("[data-rmc-autosubmit-hide-when-js]").forEach(function (btn) {
        btn.setAttribute("hidden", "");
      });

      var pending = null;
      function submit() {
        try { form.submit(); } catch (_e) {}
      }

      form.addEventListener("change", function (e) {
        if (pending) { clearTimeout(pending); pending = null; }
        if (isInstantField(e.target)) {
          submit();
        } else {
          pending = setTimeout(submit, DEBOUNCE_MS);
        }
      });

      // For text inputs, fire on input (debounced) so search-as-you-type works.
      form.addEventListener("input", function (e) {
        if (isInstantField(e.target)) { return; }
        if (pending) { clearTimeout(pending); }
        pending = setTimeout(submit, DEBOUNCE_MS);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
