"""Quarterly security posture → finance.Notification + corner toast payload."""

from __future__ import annotations

import logging
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.profile_security_evaluation import is_security_posture_review_due

logger = logging.getLogger(__name__)

POSTURE_NOTIFICATION_TITLE = "Quarterly security review due"
SESSION_CORNER_SNOOZE_KEY = "rmc_security_posture_corner_snoozed"


def is_corner_snoozed(request) -> bool:
    return bool(getattr(request, "session", None) and request.session.get(SESSION_CORNER_SNOOZE_KEY))


def snooze_corner_notifications(request) -> None:
    if getattr(request, "session", None) is not None:
        request.session[SESSION_CORNER_SNOOZE_KEY] = True


def clear_corner_snooze(request) -> None:
    if getattr(request, "session", None) is not None:
        request.session.pop(SESSION_CORNER_SNOOZE_KEY, None)


def ensure_quarterly_posture_notification(user, school=None):
    """Create or return unread quarterly posture notification for inbox + corner."""
    if not user or not getattr(user, "pk", None):
        return None
    if not is_security_posture_review_due(user, school):
        return None
    try:
        from apps.finance.models import Notification

        review_url = reverse("accounts:security_posture_review")
        existing = (
            Notification.objects.filter(
                recipient=user,
                title=POSTURE_NOTIFICATION_TITLE,
                is_read=False,
            )
            .order_by("-created_at")
            .first()
        )
        if existing:
            return existing
        return Notification.objects.create(
            recipient=user,
            title=POSTURE_NOTIFICATION_TITLE,
            message=_(
                "Confirm your password, MFA, and contact details for this quarter."
            ),
            link=review_url,
            severity=Notification.Severity.WARNING,
            created_by=None,
        )
    except Exception:  # noqa: BLE001
        logger.debug("ensure_quarterly_posture_notification failed", exc_info=True)
        return None


def build_corner_notification_payload(notification, *, review_url: str) -> dict[str, Any]:
    """Serializable payload for rmc-notification-corner.js."""
    return {
        "id": str(notification.pk),
        "title": notification.title,
        "message": notification.message,
        "type": "warning",
        "href": review_url or (notification.link or ""),
        "duration_ms": 120000,
        "actions": ["read", "snooze", "dismiss"],
        "inbox_url": reverse("accounts:user_notifications"),
    }


def inline_security_posture_banner_active(request) -> bool:
    """True when the collapsible inline banner should render (corner toast suppressed)."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False) or is_corner_snoozed(request):
        return False
    school = getattr(request, "school", None)
    return is_security_posture_review_due(user, school)


def corner_notifications_for_request(request) -> list[dict[str, Any]]:
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False) or is_corner_snoozed(request):
        return []
    if inline_security_posture_banner_active(request):
        return []
    school = getattr(request, "school", None)
    if not is_security_posture_review_due(user, school):
        return []
    try:
        review_url = reverse("accounts:security_posture_review")
    except Exception:  # noqa: BLE001
        return []
    note = ensure_quarterly_posture_notification(user, school)
    if not note:
        return []
    return [build_corner_notification_payload(note, review_url=review_url)]
