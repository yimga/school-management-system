"""First-visit portal-ready corner toast (unread inbox → corner + local notify)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError
from django.urls import reverse

logger = logging.getLogger(__name__)

SESSION_DISMISSED_KEY = "rmc_portal_ready_corner_dismissed"


def _dismissed_ids(request) -> set[str]:
    session = getattr(request, "session", None)
    if not session:
        return set()
    raw = session.get(SESSION_DISMISSED_KEY) or []
    return {str(item) for item in raw if item}


def mark_portal_ready_corner_dismissed(request, notification_id: str) -> None:
    session = getattr(request, "session", None)
    if not session or not notification_id:
        return
    ids = list(_dismissed_ids(request))
    nid = str(notification_id)
    if nid not in ids:
        ids.append(nid)
    session[SESSION_DISMISSED_KEY] = ids[-30:]
    session.modified = True


def portal_ready_corner_for_request(request) -> list[dict[str, Any]]:
    """Surface unread portal-ready inbox row as a one-time corner toast."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return []
    try:
        from apps.finance.models import Notification
        from apps.schools.signup_portal_channel_notifications import (
            PORTAL_READY_INBOX_TITLE,
        )
    except ImportError:
        return []

    try:
        note = (
            Notification.objects.filter(
                recipient=user,
                title=PORTAL_READY_INBOX_TITLE,
                is_read=False,
            )
            .order_by("-created_at")
            .first()
        )
    except DatabaseError:
        logger.warning(
            "portal_ready_corner_for_request: finance_notification schema drift",
            exc_info=True,
        )
        return []
    if not note:
        return []
    nid = str(note.pk)
    if nid in _dismissed_ids(request):
        return []

    href = (note.link or "").strip()
    if not href:
        try:
            href = reverse("accounts:user_notifications")
        except Exception:  # noqa: BLE001
            href = ""

    return [
        {
            "id": nid,
            "dedup_key": "portal-ready",
            "title": note.title,
            "message": note.message,
            "type": "success",
            "href": href,
            "duration_ms": 180000,
            "actions": ["read", "dismiss"],
            "inbox_url": reverse("accounts:user_notifications"),
            "browser_notify": True,
            "source": "portal_ready",
        }
    ]


def nudge_portal_ready_web_push(user) -> int:
    """After first push subscribe, deliver portal-ready push if inbox still unread."""
    if not user or not getattr(user, "pk", None):
        return 0
    try:
        from apps.finance.models import Notification
        from apps.communication.web_push_service import send_web_push_to_user
        from apps.schools.signup_portal_channel_notifications import (
            PORTAL_READY_INBOX_TITLE,
        )
    except ImportError:
        return 0

    try:
        note = (
            Notification.objects.filter(
                recipient=user,
                title=PORTAL_READY_INBOX_TITLE,
                is_read=False,
            )
            .order_by("-created_at")
            .first()
        )
    except DatabaseError:
        logger.warning(
            "nudge_portal_ready_web_push: finance_notification schema drift",
            exc_info=True,
        )
        return 0
    if not note:
        return 0
    href = (note.link or "").strip()
    return send_web_push_to_user(
        user,
        title=note.title,
        body=note.message,
        url=href,
        tag=f"portal-ready-nudge:{note.pk}",
    )
