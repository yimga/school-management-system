// RunMyCampus message outbox (audit residual: offline messaging compose).
//
// Lets a user compose an in-app message while OFFLINE and have it actually
// delivered on reconnect. It rides the existing WAL rail (window.rmcWAL) on the
// `communication_send` domain, whose server writer creates a real
// apps.communication.Message (sender derived server-side from the socket — the
// client cannot forge a sender). Online submits are untouched (normal POST).
//
// Opt-in per form:
//   <form ... data-rmc-message-outbox
//         data-recipient-field="recipient"   (default "recipient")
//         data-subject-field="subject"       (default "subject")
//         data-body-field="body"             (default "body")
//         data-success-url="/portal/messages/?tab=direct">
//
// When the form submits and the browser is offline (or the WAL socket can't be
// reached), we enqueue the message and show an inline "queued" notice instead
// of letting the POST fail. When online we do nothing and the normal POST runs.

(function () {
  "use strict";
  if (window.rmcMessageOutbox) return;

  function fieldValue(form, name) {
    if (!name) return "";
    var el = form.elements[name];
    if (!el) return "";
    return (el.value || "").trim();
  }

  function fieldChecked(form, name) {
    if (!name) return false;
    var el = form.elements[name];
    return !!(el && el.checked);
  }

  function showQueuedNotice(form, successUrl) {
    var note = document.createElement("div");
    note.className = "alert alert-info";
    note.setAttribute("role", "status");
    note.textContent =
      "You're offline — your message was saved and will send automatically when you reconnect.";
    form.parentNode.insertBefore(note, form);
    form.reset();
    if (successUrl) {
      setTimeout(function () {
        window.location.href = successUrl;
      }, 1500);
    }
  }

  async function queueMessage(payload) {
    if (!window.rmcWAL || typeof window.rmcWAL.append !== "function") {
      return false;
    }
    var recipientId = parseInt(payload.recipientId, 10);
    if (!recipientId || !payload.body) return false;
    try {
      await window.rmcWAL.append("communication_send", [
        {
          recipient_id: recipientId,
          subject: payload.subject || "Message",
          body: payload.body,
          locale_target: payload.localeTarget || "",
        },
      ]);
      return true;
    } catch (e) {
      return false;
    }
  }

  function enhance(form) {
    if (form.__rmcMessageOutboxBound) return;
    form.__rmcMessageOutboxBound = true;
    form.addEventListener("submit", function (ev) {
      // Only intercept when the browser believes it is offline. Online submits
      // take the normal server POST path (server-rendered confirmation).
      if (navigator.onLine !== false) return;
      var recipientField = form.getAttribute("data-recipient-field") || "recipient";
      var subjectField = form.getAttribute("data-subject-field") || "subject";
      var bodyField = form.getAttribute("data-body-field") || "body";
      var body = fieldValue(form, bodyField);
      var recipientId = fieldValue(form, recipientField);
      if (!body || !recipientId) return; // let native validation handle empties
      ev.preventDefault();
      var successUrl = form.getAttribute("data-success-url") || "";
      queueMessage({
        recipientId: recipientId,
        subject: fieldValue(form, subjectField),
        body: body,
        localeTarget: form.getAttribute("data-locale-target") || "",
      }).then(function (ok) {
        if (ok) {
          showQueuedNotice(form, successUrl);
        } else {
          // Could not queue (no WAL support) — fall back to normal submit so
          // the user isn't silently blocked.
          form.submit();
        }
      });
    });
  }

  // ── Announcements ────────────────────────────────────────────────────────
  // A school-wide announcement is NOT a single-recipient Message — it fans out
  // to an audience and runs an approval FSM. It rides its own WAL domain
  // (`announcement_create`), whose server writer re-derives publish-vs-approval
  // from the authenticated author's role (a teacher's offline announcement
  // lands as PENDING_APPROVAL, never auto-published).
  //
  //   <form ... data-rmc-announcement-outbox
  //         data-title-field="title" data-content-field="content"
  //         data-type-field="announcement_type" data-audience-field="audience"
  //         data-urgent-field="is_urgent" data-success-url="...">
  async function queueAnnouncement(payload) {
    if (!window.rmcWAL || typeof window.rmcWAL.append !== "function") {
      return false;
    }
    if (!payload.title || !payload.content) return false;
    try {
      await window.rmcWAL.append("announcement_create", [
        {
          title: payload.title,
          content: payload.content,
          announcement_type: payload.announcementType || "",
          audience: payload.audience || "",
          is_urgent: !!payload.isUrgent,
        },
      ]);
      return true;
    } catch (e) {
      return false;
    }
  }

  function enhanceAnnouncement(form) {
    if (form.__rmcAnnouncementOutboxBound) return;
    form.__rmcAnnouncementOutboxBound = true;
    form.addEventListener("submit", function (ev) {
      if (navigator.onLine !== false) return;
      var titleField = form.getAttribute("data-title-field") || "title";
      var contentField = form.getAttribute("data-content-field") || "content";
      var title = fieldValue(form, titleField);
      var content = fieldValue(form, contentField);
      if (!title || !content) return; // let native validation handle empties
      ev.preventDefault();
      var successUrl = form.getAttribute("data-success-url") || "";
      queueAnnouncement({
        title: title,
        content: content,
        announcementType: fieldValue(form, form.getAttribute("data-type-field") || "announcement_type"),
        audience: fieldValue(form, form.getAttribute("data-audience-field") || "audience"),
        isUrgent: fieldChecked(form, form.getAttribute("data-urgent-field") || "is_urgent"),
      }).then(function (ok) {
        if (ok) {
          showQueuedNotice(form, successUrl);
        } else {
          form.submit();
        }
      });
    });
  }

  function init() {
    document.querySelectorAll("form[data-rmc-message-outbox]").forEach(enhance);
    document
      .querySelectorAll("form[data-rmc-announcement-outbox]")
      .forEach(enhanceAnnouncement);
  }

  window.rmcMessageOutbox = {
    queueMessage: queueMessage,
    enhance: enhance,
    queueAnnouncement: queueAnnouncement,
    enhanceAnnouncement: enhanceAnnouncement,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
