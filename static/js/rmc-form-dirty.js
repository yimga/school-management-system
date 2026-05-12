/**
 * Dirty-state detection for forms decorated with [data-rmc-dirty-watch].
 *
 * Behavior:
 *   - Snapshots initial form values on load.
 *   - On any change, sets data-dirty="1" on the form and the .rmc-form-savebar.
 *   - Reveals [data-rmc-dirty-message] hint and warns on navigation away.
 *   - "Cancel" button [data-rmc-form-reset] restores initial snapshot.
 *
 * Markup contract:
 *   <form data-rmc-dirty-watch="1">
 *     …fields…
 *     <div class="rmc-form-savebar">
 *       <span data-rmc-dirty-message hidden>You have unsaved changes</span>
 *       <button data-rmc-form-reset>Cancel</button>
 *       <button type="submit">Save</button>
 *     </div>
 *   </form>
 */
(function () {
  "use strict";

  function snapshot(form) {
    var snap = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name) { return; }
      if (el.type === "checkbox" || el.type === "radio") {
        snap[el.name + ":" + (el.value || "")] = el.checked;
      } else {
        snap[el.name] = el.value;
      }
    });
    return snap;
  }

  function compare(a, b) {
    for (var k in a) { if (a[k] !== b[k]) { return true; } }
    for (var k2 in b) { if (b[k2] !== a[k2]) { return true; } }
    return false;
  }

  function setDirty(form, dirty) {
    form.setAttribute("data-dirty", dirty ? "1" : "0");
    var bar = form.querySelector(".rmc-form-savebar");
    if (bar) { bar.setAttribute("data-dirty", dirty ? "1" : "0"); }
    var hint = form.querySelector("[data-rmc-dirty-message]");
    if (hint) { if (dirty) { hint.removeAttribute("hidden"); } else { hint.setAttribute("hidden", ""); } }
  }

  function init() {
    var forms = document.querySelectorAll("form[data-rmc-dirty-watch]");
    forms.forEach(function (form) {
      var initial = snapshot(form);
      function check() {
        setDirty(form, compare(initial, snapshot(form)));
      }
      form.addEventListener("input", check);
      form.addEventListener("change", check);
      form.addEventListener("submit", function () {
        /* Submit clears the dirty flag immediately so beforeunload doesn't fire. */
        setDirty(form, false);
      });
      var resetBtn = form.querySelector("[data-rmc-form-reset]");
      if (resetBtn) {
        resetBtn.addEventListener("click", function (e) {
          e.preventDefault();
          Array.prototype.forEach.call(form.elements, function (el) {
            if (!el.name) { return; }
            if (el.type === "checkbox" || el.type === "radio") {
              var key = el.name + ":" + (el.value || "");
              if (key in initial) { el.checked = initial[key]; }
            } else if (el.name in initial) {
              el.value = initial[el.name];
            }
          });
          setDirty(form, false);
        });
      }
    });

    window.addEventListener("beforeunload", function (e) {
      var anyDirty = document.querySelector("form[data-rmc-dirty-watch][data-dirty='1']");
      if (anyDirty) {
        e.preventDefault();
        e.returnValue = "";
        return "";
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
