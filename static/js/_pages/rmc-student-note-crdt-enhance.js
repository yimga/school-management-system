/* Progressive CRDT enhancement for counselor student-note drafts.
 *
 * Metric 25: mirror lesson-plan Client callers for policy_registry student_note.
 * Progressive: no-op when window.rmcCRDT is missing. Native form submit remains
 * the source of truth; CRDT only mirrors draft note text.
 *
 * Idempotent via window.__rmcStudentNoteCRDTBound.
 */
(function () {
  "use strict";
  if (window.__rmcStudentNoteCRDTBound) return;
  window.__rmcStudentNoteCRDTBound = true;

  function actorId() {
    var fromMeta = document.querySelector('meta[name="rmc-user-id"]');
    if (fromMeta && fromMeta.content) return "user-" + fromMeta.content;
    var body = document.body;
    if (body && body.dataset && body.dataset.rmcUserId) {
      return "user-" + body.dataset.rmcUserId;
    }
    return "browser-student-note";
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
    var forms = document.querySelectorAll('form[data-rmc-crdt-entity="student_note"]');
    if (!forms.length) return;

    var client = new window.rmcCRDT.Client({ actorId: actorId() });
    window.__rmcStudentNoteCRDTClient = client;

    function flushField(el) {
      var key = el.getAttribute("data-rmc-crdt-key");
      if (!key) return;
      var value = (el.value || "").toString();
      client.lwwSet("student_note", key, value);
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

    forms.forEach(function (form) {
      var fields = form.querySelectorAll("[data-rmc-crdt-key]");
      fields.forEach(function (el) {
        el.addEventListener("blur", function () {
          flushField(el);
        });
        el.addEventListener("input", onChange);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
