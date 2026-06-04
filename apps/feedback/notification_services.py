"""Feedback notification helpers — email + platform event bus (batch 1519)."""

from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.feedback.models import FeedbackSubmission

logger = logging.getLogger(__name__)
User = get_user_model()


def _user_emails(users: Iterable) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for user in users:
        email = (getattr(user, "email", "") or "").strip().lower()
        if email and email not in seen:
            seen.add(email)
            out.append(email)
    return out


def send_quiet(*, subject: str, body: str, recipients: list[str]) -> int:
    if not recipients:
        return 0
    try:
        from apps.schoolops.email_compat import send_mail

        return send_mail(
            subject=subject,
            message=body,
            from_email=None,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception as exc:
        logger.warning(
            "feedback notification email failed (%s recipients): %s",
            len(recipients),
            exc,
        )
        return 0


def operator_alert_recipients() -> list[str]:
    raw = (
        getattr(settings, "OPERATOR_ALERT_EMAIL", "")
        or getattr(settings, "MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL", "")
        or ""
    ).strip()
    if not raw:
        return []
    return [addr.strip().lower() for addr in raw.split(",") if addr.strip()]


def school_admin_recipients(school) -> list[str]:
    if school is None:
        return []
    try:
        from apps.schools.models import SchoolMembership
    except Exception:
        return []
    # tenant-isolation-allow: feedback-alert-school-admin-membership-by-school
    memberships = SchoolMembership.objects.filter(
        school=school,
        role__in=("ADMIN", "PROPRIETOR"),
    ).select_related("user")
    users = [m.user for m in memberships if getattr(m, "user", None)]
    return _user_emails(users)


def publish_feedback_bus_event(feedback: FeedbackSubmission, *, event_suffix: str) -> None:
    try:
        from apps.platform_runtime.event_bus import publish_event
    except Exception:
        return
    try:
        publish_event(
            f"feedback.submission.{event_suffix}",
            {
                "feedback_id": feedback.pk,
                "severity": feedback.severity,
                "category": feedback.category,
                "school_id": feedback.school_id,
                "title": (feedback.title or "")[:180],
            },
            school_id=feedback.school_id,
            strict_catalog=False,
            source="apps.feedback.notification_services",
        )
    except Exception:
        logger.warning("feedback bus publish failed feedback_id=%s", feedback.pk, exc_info=True)


def notify_critical_feedback_submission(feedback: FeedbackSubmission) -> None:
    """Operator + school admin alert for new critical/high submissions."""
    if feedback.severity not in (
        FeedbackSubmission.Severity.CRITICAL,
        FeedbackSubmission.Severity.HIGH,
    ):
        return
    school_name = getattr(feedback.school, "name", None) or "unknown school"
    title = (feedback.title or "Feedback").strip()
    body = (
        f"A {feedback.severity} feedback submission was received.\n\n"
        f"School: {school_name}\n"
        f"Category: {feedback.get_category_display()}\n"
        f"Title: {title}\n"
        f"Feedback ID: {feedback.pk}\n\n"
        "Review in the feedback operator console.\n"
    )
    recipients = operator_alert_recipients() + school_admin_recipients(feedback.school)
    send_quiet(
        subject=f"[{feedback.severity.upper()}] Feedback: {title[:60]}",
        body=body,
        recipients=recipients,
    )
    publish_feedback_bus_event(
        feedback,
        event_suffix="critical" if feedback.severity == FeedbackSubmission.Severity.CRITICAL else "high",
    )
