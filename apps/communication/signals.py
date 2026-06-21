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

from apps.communication.models import Message, ThreadMessage, ThreadMute

logger = logging.getLogger(__name__)

#: Per-message cap on the group-thread notification fan-out — a defensive bound so
#: one post to a very large group can't spawn an unbounded dispatch loop.
GROUP_MESSAGE_MAX_FANOUT = 500  # magic-number-allow: group message notification fan-out cap

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

        # If the recipient has blocked the sender, suppress the notification
        # (the send itself is refused at the view; this is defense in depth — IM-7).
        try:
            from apps.communication.models import MessageBlock

            sender_id = getattr(instance, "sender_id", None)
            # tenant-isolation-allow: block-row-scoped-to-this-recipient-sender-pair
            if sender_id and MessageBlock.objects.filter(
                blocker_id=recipient_id, blocked_id=sender_id
            ).exists():
                return
        except Exception:  # noqa: BLE001 — a block lookup must never break the send
            pass

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


@receiver(
    post_save,
    sender=ThreadMessage,
    dispatch_uid="communication_thread_message_notify",
)
def notify_on_thread_message(sender, instance, created, **kwargs):  # noqa: ARG001
    """Notify a group thread's members of a newly-posted message (IM-2).

    Group messages use :class:`ThreadMessage`, which had NO ``post_save`` receiver,
    so posting in a group notified nobody — not in-app, push, or email. This
    mirrors :func:`notify_on_message_received` but fans the event to every thread
    member except the author, each routed through
    :func:`apps.communication.dispatch.dispatch_event` on the ``message.received``
    key so each member's MESSAGES-category preferences (mute / channels / quiet
    hours) apply.

    Created-only, on_commit-deferred, PII-safe (logs error *type* only), and the
    fan-out is bounded by :data:`GROUP_MESSAGE_MAX_FANOUT`. The in-app transport's
    unread ``(recipient, title)`` constraint collapses repeated posts to the same
    thread into one unread row until the member reads it.
    """
    try:
        if not created:
            return
        thread = getattr(instance, "thread", None)
        if thread is None:
            return
        author_id = getattr(instance, "author_id", None)
        school = getattr(thread, "school", None)

        thread_title = (getattr(thread, "title", "") or "").strip() or "a group"
        title = f"New message in {thread_title}"
        author_name = _sender_display_name(getattr(instance, "author", None))
        raw = (instance.content or "").strip()
        preview = raw[:MESSAGE_PREVIEW_CHARS]
        if len(raw) > MESSAGE_PREVIEW_CHARS:
            preview += "..."
        try:
            from django.urls import reverse

            link = reverse("communication:group_detail", args=[thread.pk])
        except Exception:  # noqa: BLE001 — missing/renamed URL must not break the send
            link = ""

        context = {
            "title": title,
            "message": preview,
            "link": link,
            "severity": "INFO",
        }

        # Members who muted this thread get no "new message" notification (IM-7).
        # A direct @mention still reaches them — that path is separate.
        try:
            # tenant-isolation-allow: mutes-scoped-to-this-threads-own-mute-rows
            muted_ids = set(
                ThreadMute.objects.filter(thread=thread).values_list(
                    "user_id", flat=True
                )
            )
        except Exception:  # noqa: BLE001 — a mute lookup must never break the send
            muted_ids = set()

        # Snapshot the non-muted, non-author member ids up-front so the deferred
        # closure doesn't depend on a lazily-evaluated M2M. Bounded fan-out.
        try:
            member_ids = list(
                thread.members.exclude(pk=author_id)
                .exclude(pk__in=muted_ids)
                .values_list("pk", flat=True)[:GROUP_MESSAGE_MAX_FANOUT]
            )
        except Exception:  # noqa: BLE001 — a bad membership relation never breaks save
            member_ids = []

        mention_title = f"{author_name} mentioned you in {thread_title}"

        def _dispatch():
            from apps.communication.dispatch import dispatch_event
            from apps.communication.models import ThreadMessageMention
            from django.contrib.auth import get_user_model

            user_model = get_user_model()

            # @mentions are recorded by the posting view before commit, so they're
            # visible here. Mentioned members get a distinct, mute-piercing
            # "mentioned you" notification; everyone else (non-muted, non-mentioned)
            # gets the plain "new message" one — so nobody is double-notified, and
            # a muted member is still reachable by an explicit @mention.
            try:
                # tenant-isolation-allow: mentions-scoped-to-this-committed-message-row
                mentioned_ids = set(
                    ThreadMessageMention.objects.filter(
                        message_id=instance.pk
                    ).values_list("user_id", flat=True)
                )
            except Exception:  # noqa: BLE001 — mention lookup must never break dispatch
                mentioned_ids = set()
            mentioned_ids.discard(author_id)

            regular_ids = [mid for mid in member_ids if mid not in mentioned_ids]

            # tenant-isolation-allow: recipient-ids-derived-from-this-threads-own-membership
            for member in user_model.objects.filter(pk__in=regular_ids):
                try:
                    dispatch_event(
                        "message.received",
                        recipient=member,
                        context=context,
                        school=school,
                    )
                except Exception as exc:  # noqa: BLE001 — never break post-commit hooks
                    logger.warning(
                        "thread.message dispatch failed err=%s", type(exc).__name__
                    )

            if mentioned_ids:
                mention_context = {
                    "title": mention_title,
                    "message": preview,
                    "link": link,
                    "severity": "INFO",
                }
                bounded = list(mentioned_ids)[:GROUP_MESSAGE_MAX_FANOUT]
                # tenant-isolation-allow: mention-recipient-ids-are-this-threads-own-members
                for member in user_model.objects.filter(pk__in=bounded):
                    try:
                        dispatch_event(
                            "message.received",
                            recipient=member,
                            context=mention_context,
                            school=school,
                        )
                    except Exception as exc:  # noqa: BLE001 — never break post-commit hooks
                        logger.warning(
                            "thread.mention dispatch failed err=%s",
                            type(exc).__name__,
                        )

        # Always defer: even with no plain recipients there may be mentioned
        # (and muted) members to notify, which are only known post-commit.
        transaction.on_commit(_dispatch)

    except Exception as exc:  # noqa: BLE001 — a notification must never break save()
        logger.warning(
            "thread.message signal failed err=%s", type(exc).__name__
        )
