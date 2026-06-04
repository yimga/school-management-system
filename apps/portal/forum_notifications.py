"""Email notifications for community forum replies (batch 1360)."""

from __future__ import annotations

import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from apps.schoolops.email_compat import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from apps.portal.models_forums import CommunityForumReply

logger = logging.getLogger(__name__)
User = get_user_model()


def _user_wants_forum_email(user) -> bool:
    if not user or not getattr(user, "is_active", True):
        return False
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False
    try:
        from apps.portal.portal_models import PortalPreferences

        prefs = PortalPreferences.objects.filter(parent_id=user.pk).first()
        if prefs is not None and not prefs.notification_email:
            return False
    except Exception:
        pass
    return True


def forum_reply_recipient_ids(reply: CommunityForumReply) -> list[int]:
    """Topic author + prior repliers, excluding the replier."""
    topic = reply.topic
    replier_id = reply.author_id
    ids: set[int] = set()
    if topic.author_id and topic.author_id != replier_id:
        ids.add(topic.author_id)
    for author_id in (
        topic.replies.exclude(author_id__isnull=True)
        .values_list("author_id", flat=True)
        .distinct()
    ):
        if author_id and author_id != replier_id:
            ids.add(author_id)
    return sorted(ids)


def send_forum_reply_notifications(
    reply_id: int,
    *,
    topic_url: str = "",
) -> dict[str, int]:
    """
    Send one email per eligible recipient. Never raises — logs warnings only.
    """
    reply = (
        CommunityForumReply.objects.select_related(
            "topic", "topic__school", "topic__category", "author"
        )
        .filter(pk=reply_id)
        .first()
    )
    if reply is None:
        return {"sent": 0, "skipped": 0, "errors": 0}

    topic = reply.topic
    school_name = getattr(topic.school, "name", None) or "your school"
    recipient_ids = forum_reply_recipient_ids(reply)
    if not recipient_ids:
        return {"sent": 0, "skipped": 0, "errors": 0}

    if not topic_url:
        try:
            topic_url = reverse("portal:forum_topic", kwargs={"topic_id": topic.pk})
        except Exception:
            topic_url = f"/portal/forums/topic/{topic.pk}/"

    replier_label = ""
    if reply.author:
        replier_label = (
            reply.author.get_full_name() or reply.author.username or ""
        ).strip()

    ctx = {
        "school_name": school_name,
        "topic_title": topic.title,
        "topic_url": topic_url,
        "reply_excerpt": (reply.body or "")[:400],
        "replier_name": replier_label or "A community member",
        "reply_count": topic.reply_count,
    }

    from_email = getattr(
        settings, "DEFAULT_FROM_EMAIL", "no-reply@runmycampus.com"
    )
    subject = f"[{school_name}] New reply: {topic.title[:120]}"
    sent = skipped = errors = 0

    for user in User.objects.filter(pk__in=recipient_ids):
        if not _user_wants_forum_email(user):
            skipped += 1
            continue
        try:
            send_mail(
                subject=subject,
                message=render_to_string(
                    "portal/email/forum_reply_notification.txt", ctx
                ),
                from_email=from_email,
                recipient_list=[user.email],
                html_message=render_to_string(
                    "portal/email/forum_reply_notification.html", ctx
                ),
                fail_silently=False,
            )
            sent += 1
        except Exception:
            errors += 1
            logger.warning(
                "forum_reply_notification_failed topic_id=%s reply_id=%s user_id=%s",
                topic.pk,
                reply.pk,
                user.pk,
                exc_info=True,
            )

    return {"sent": sent, "skipped": skipped, "errors": errors}


def queue_forum_reply_notifications(
    reply: CommunityForumReply,
    *,
    request=None,
) -> None:
    """Enqueue Celery task; fall back to in-process send when broker absent."""
    topic_url = ""
    if request is not None:
        try:
            topic_url = request.build_absolute_uri(
                reverse("portal:forum_topic", kwargs={"topic_id": reply.topic_id})
            )
        except Exception:
            topic_url = ""
    try:
        from apps.portal.tasks import notify_forum_reply_task

        notify_forum_reply_task.delay(reply.pk, topic_url=topic_url)
    except Exception:
        send_forum_reply_notifications(reply.pk, topic_url=topic_url)
