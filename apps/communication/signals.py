"""Communication app signals (MED-6).

A received inbox :class:`~apps.communication.models.Message` previously fired
*no* notification — there was no ``post_save`` on ``Message`` — so a 1:1 direct
message only surfaced if the recipient happened to open their inbox. This module
closes that gap by routing genuine, deliverable direct messages through the
Phase-3 :func:`apps.communication.dispatch.dispatch_event` router (the single
event → preference → channel path; no hand-rolled channel logic here).

Design notes honoured:

* **Created-only / idempotent enough** — fires on ``created is True`` only, so an
  edit / mark-as-read save never re-notifies. The in-app transport additionally
  dedupes on the unread ``(recipient, title)`` constraint, so this title format
  intentionally matches the legacy in-view helper to collapse into one row.
* **Broadcasts excluded for free** — broadcast / bulk fan-out rows are written via
  ``Message.objects.bulk_create(...)`` (see ``api_views.py``), which does **not**
  emit ``post_save``. This receiver therefore never fires for broadcast rows — no
  extra guard is needed (this comment documents why).
* **PII-safe logging** — on failure we log the *exception type only*, never the
  subject / body / recipient (there is a pii-logging-smell gate).
* **Transaction-safe** — the whole body is wrapped in a broad ``try/except`` so a
  notification failure can never break the message save, and the dispatch is
  deferred with :func:`~django.db.transaction.on_commit` so it sees a persisted
  row and runs *outside* the sender's transaction.
* **Tenant-scoped** — ``school`` is threaded through to ``dispatch_event``.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.communication.models import Message

logger = logging.getLogger(__name__)

#: Body-preview length cap for the notification message (named, not a literal at
#: the call site). Kept short so the in-app/push payload stays a teaser, not the
#: full body (also bounded by the Notification.message field downstream).
MESSAGE_PREVIEW_CHARS = 140  # magic-number-allow: in-app/push message preview length


def _sender_display_name(sender) -> str:
    """Resolve a human-friendly sender name without ever raising.

    Prefers ``get_full_name()`` (trimmed), then ``username``, then a neutral
    ``"Someone"`` fallback (used for a system/sender-less message). Never returns
    an empty string.
    """
    if sender is None:
        return "Someone"
    try:
        full = (sender.get_full_name() or "").strip()
        if full:
            return full
    except Exception:  # noqa: BLE001 — name resolution must never break the send
        pass
    username = (getattr(sender, "username", "") or "").strip()
    return username or "Someone"


def _thread_link(sender) -> str:
    """Best-effort direct-thread URL for the recipient → ``""`` if not reversible.

    The recipient's view of the conversation is keyed by the *other* user (the
    sender), matching ``accounts:direct_thread`` (``messages/direct/<user_id>/``).
    Never raises — an un-reversible / missing URL just yields an empty link.
    """
    sender_pk = getattr(sender, "pk", None)
    if not sender_pk:
        return ""
    try:
        from django.urls import reverse

        return reverse("accounts:direct_thread", args=[sender_pk])
    except Exception:  # noqa: BLE001 — missing/renamed URL must not break the send
        return ""


@receiver(post_save, sender=Message, dispatch_uid="communication_message_received_notify")
def notify_on_message_received(sender, instance, created, **kwargs):  # noqa: ARG001
    """Notify the recipient of a newly-created, deliverable direct message.

    Fires ONLY when all of the following hold (a genuine deliverable DM):

    * ``created is True`` — never on an update (mark-read / edit / archive save);
    * ``instance.recipient_id`` is set — a real recipient to notify;
    * ``instance.sender_id != instance.recipient_id`` — no self-notification;
    * ``not instance.is_archived`` — an archived-on-create row is not surfaced.

    Broadcast rows arrive via ``bulk_create`` and never reach this receiver, so
    they are correctly excluded without an explicit guard.
    """
    try:
        # --- created-only + deliverable-DM guards (idempotent / no self-notify) ---
        if not created:
            return
        recipient_id = getattr(instance, "recipient_id", None)
        if not recipient_id:
            return
        if getattr(instance, "sender_id", None) == recipient_id:
            return
        if getattr(instance, "is_archived", False):
            return

        recipient = instance.recipient
        message_sender = getattr(instance, "sender", None)
        school = getattr(instance, "school", None)

        # Build the notification payload (PII stays in the payload, never logged).
        title = f"New message from {_sender_display_name(message_sender)}"
        raw_preview = (instance.subject or "") or (instance.body or "")
        raw_preview = raw_preview.strip()
        preview = raw_preview[:MESSAGE_PREVIEW_CHARS]
        if len(raw_preview) > MESSAGE_PREVIEW_CHARS:
            preview += "..."
        link = _thread_link(message_sender)

        context = {
            "title": title,
            "message": preview,
            "link": link,
            "severity": "INFO",
        }

        # Defer to after the row is committed so the dispatch sees a persisted
        # message and never runs inside the sender's open transaction. The lambda
        # body is itself failure-isolated below via the outer try/except + the
        # router's own per-channel isolation.
        def _dispatch():
            from apps.communication.dispatch import dispatch_event

            try:
                dispatch_event(
                    "message.received",
                    recipient=recipient,
                    context=context,
                    school=school,
                )
            except Exception as exc:  # noqa: BLE001 — never break post-commit hooks
                # PII-safe: error *type* only, never subject/body/recipient.
                logger.warning(
                    "message.received dispatch failed err=%s",
                    type(exc).__name__,
                )

        transaction.on_commit(_dispatch)

    except Exception as exc:  # noqa: BLE001 — a notification must never break save()
        # PII-safe: error *type* only, never subject/body/recipient.
        logger.warning(
            "message.received signal failed err=%s",
            type(exc).__name__,
        )
