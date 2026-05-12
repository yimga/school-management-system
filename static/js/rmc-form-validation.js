/**
 * Form validation polish — spring-shake + scroll-to-first-error + auto-focus.
 *
 * Listens for `invalid` events bubbling from any input within a form. On a
 * blocked submit (HTML5 reportValidity()), the first invalid field shakes,
 * the page scrolls it into view, and focus moves there.
 *
 * Marks fields with `.is-invalid` (Bootstrap-compatible) as soon as the
 * `invalid` event fires, so the polished error styling (red border, tinted
 * halo) shows up immediately. Class is removed on `input`/`change` so the
 * user gets live feedback when correcting.
 *
 * Server-rendered `.is-invalid` (from Django form errors) still works —
 * we just augment with the spring-shake on page load if any are present.
 *
 * Honors prefers-reduced-motion (no shake; still scrolls + focuses).
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  function shake(el) {
    if (!el) return;
    el.classList.remove("rmc-shake");
    /* Reflow so the animation restarts on repeated submits. */
    void el.offsetWidth;
    el.classList.add("rmc-shake");
    setTimeout(function () { el.classList.remove("rmc-shake"); }, 500);
  }

  function scrollToField(el) {
    if (!el) return;
    if (typeof el.scrollIntoView === "function") {
      try { el.scrollIntoView({ behavior: "smooth", block: "center" }); }
      catch (_) { el.scrollIntoView(); }
    }
  }

  function onInvalid(e) {
    var field = e.target;
    if (!field || !field.matches) return;
    if (!field.matches("input, select, textarea")) return;
    field.classList.add("is-invalid");
    /* Only the FIRST invalid field in the burst gets focus + scroll — the
       browser fires `invalid` for every blocking field; we de-dupe by
       checking whether any other field was already handled this frame. */
    if (onInvalid._handled) return;
    onInvalid._handled = true;
    requestAnimationFrame(function () { onInvalid._handled = false; });
    shake(field);
    scrollToField(field);
    /* Defer focus so the scroll completes first. */
    setTimeout(function () {
      if (document.activeElement !== field) {
        try { field.focus({ preventScroll: true }); } catch (_) { field.focus(); }
      }
    }, 60);
  }

  function onCorrect(e) {
    var field = e.target;
    if (!field || !field.classList || !field.classList.contains("is-invalid")) return;
    /* Don't clear until the field is actually valid (HTML5 + custom). */
    if (field.checkValidity && !field.checkValidity()) return;
    field.classList.remove("is-invalid");
  }

  /* `invalid` doesn't bubble by default; use capture phase. */
  document.addEventListener("invalid", onInvalid, true);
  document.addEventListener("input", onCorrect, true);
  document.addEventListener("change", onCorrect, true);

  /* Server-rendered errors: shake the first one once. */
  function shakeServerErrors() {
    var firstError = document.querySelector(".is-invalid, .has-error");
    if (firstError) shake(firstError);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", shakeServerErrors);
  } else {
    shakeServerErrors();
  }
})();
