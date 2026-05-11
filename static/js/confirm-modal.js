/* Pass 8 Wave 2 — wire `components/confirm_modal.html` to either submit the
 * triggering form or follow a `data-confirm-href` URL when the user clicks
 * the confirm button.
 *
 * Patterns supported:
 *   1. Trigger inside a form (button or link with [data-prevent-submit]):
 *      modal opens → click confirm → the parent form submits.
 *
 *   2. Trigger as a standalone link with [data-confirm-href]:
 *      modal opens → click confirm → window.location = data-confirm-href.
 *
 * The trigger element is captured via Bootstrap's `relatedTarget` on the
 * `show.bs.modal` event. The confirm button on the modal stores that
 * trigger so the click handler knows what to do.
 *
 * Designed to coexist with htmx — if the trigger has hx-* attributes,
 * we let Bootstrap finish closing the modal and let htmx submit normally
 * (it picks up the click as if the modal weren't there).
 */
(function () {
  "use strict";

  function init() {
    document.querySelectorAll('[data-confirm-action]').forEach(function (confirmBtn) {
      if (confirmBtn.dataset.confirmActionWired === "1") return;
      confirmBtn.dataset.confirmActionWired = "1";

      var modal = confirmBtn.closest(".modal");
      if (!modal) return;

      // Capture the trigger element when the modal opens.
      modal.addEventListener("show.bs.modal", function (event) {
        var trigger = event.relatedTarget;
        if (trigger) {
          modal._confirmTrigger = trigger;
        }
      });

      // On click, decide whether to submit a form or navigate.
      confirmBtn.addEventListener("click", function () {
        var trigger = modal._confirmTrigger;
        if (!trigger) return;

        // Pattern 2 — explicit href.
        var href = trigger.getAttribute("data-confirm-href");
        if (href) {
          window.location.assign(href);
          return;
        }

        // Pattern 1 — submit the surrounding form.
        var form = trigger.closest("form");
        if (form) {
          // If trigger is a submit button with a name/value, replicate it as a
          // hidden input so the form action receives the same payload it would
          // have if the trigger button were clicked directly.
          if (trigger.tagName === "BUTTON" && trigger.name) {
            var hidden = document.createElement("input");
            hidden.type = "hidden";
            hidden.name = trigger.name;
            hidden.value = trigger.value || "";
            form.appendChild(hidden);
          }
          form.submit();
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
