/* Progressive CRDT enhancement for teacher lesson-plan drafts.
 *
 * Metric 25 residual: window.rmcCRDT was loaded in portal_base but had 0
 * callers. This script constructs a Client and pushes LWW ops for fields
 * marked data-rmc-crdt-key on a form with data-rmc-crdt-entity="lesson_plan".
 *
 * Progressive: no-op when window.rmcCRDT is missing. Native form submit
 * remains the source of truth for file upload; CRDT only mirrors draft text.
 *
 * Idempotent via window.__rmcLessonPlanCRDTBound.
 */
(function () {
  "use strict";
  if (window.__rmcLessonPlanCRDTBound) return;
  window.__rmcLessonPlanCRDTBound = true;

  function actorId() {
    var fromMeta = document.querySelector('meta[name="rmc-user-id"]');
    if (fromMeta && fromMeta.content) return "user-" + fromMeta.content;
    var body = document.body;
    if (body && body.dataset && body.dataset.rmcUserId) {
      return "user-" + body.dataset.rmcUserId;
    }
    return "browser-lesson-plan";
  }

  function debounce(fn, ms) {
    var t = null;
    return function () {
      var ctx = this;
      var args = arguments;
      if (t) clearTimeout(t);
      t = setTimeout(function () {
        fn.apply(ctx, args);
      }, ms);
    };
  }

  function wire() {
    if (!window.rmcCRDT || typeof window.rmcCRDT.Client !== "function") return;
    var form = document.querySelector('form[data-rmc-crdt-entity="lesson_plan"]');
    if (!form) return;
    var entity = form.getAttribute("data-rmc-crdt-entity") || "lesson_plan";
    var fields = form.querySelectorAll("[data-rmc-crdt-key]");
    if (!fields.length) return;

    var client = new window.rmcCRDT.Client({ actorId: actorId() });
    window.__rmcLessonPlanCRDTClient = client;

    function flushField(el) {
      var key = el.getAttribute("data-rmc-crdt-key");
      if (!key) return;
      var value = (el.value || "").toString();
      client.lwwSet(entity, key, value);
      if (typeof client.pushOps === "function") {
        client.pushOps().catch(function () {
          /* queue preserved for retry; native submit still works */
        });
      }
    }

    var onChange = debounce(function (ev) {
      var el = ev && ev.target;
      if (!el || !el.getAttribute || !el.getAttribute("data-rmc-crdt-key")) return;
      flushField(el);
    }, 400);

    fields.forEach(function (el) {
      el.addEventListener("blur", function () {
        flushField(el);
      });
      el.addEventListener("input", onChange);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
