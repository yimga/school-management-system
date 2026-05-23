"""Server-owned notification intents — never client SMTP (SODP batch 1407)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from django.contrib.auth import get_user_model

from apps.platform_runtime.offline_action_types import validate_offline_payload

logger = logging.getLogger(__name__)

_TEMPLATE_RENDERERS: dict[str, str] = {
    "low_meal_balance": "schoolops/email/locale/{locale}/low_meal_balance",
    "exam_readiness": "schoolops/email/locale/{locale}/exam_readiness",
    "fee_reminder": "schoolops/email/locale/{locale}/fee_reminder",
    "transport_delay": "schoolops/email/locale/{locale}/transport_delay",
    "wellbeing_checkin": "schoolops/email/locale/{locale}/wellbeing_checkin",
}


def _hash_tenant(school_id: int) -> str:
    return hashlib.sha256(str(school_id).encode()).hexdigest()[:12]


def _resolve_recipient_email(*, school, recipient_user_id: str) -> Optional[str]:
    User = get_user_model()
    try:
        uid = int(recipient_user_id)
    except (TypeError, ValueError):
        return None
    user = (
        User.objects.filter(pk=uid)
        .only("email", "is_active")
        .first()
    )
    if user is None or not user.is_active:
        return None
    email = (getattr(user, "email", None) or "").strip()
    if not email or "@" not in email:
        return None
    from apps.schools.models import SchoolMembership

    # tenant-isolation-allow: notification-intent-recipient-membership-scope
    if not SchoolMembership.objects.filter(school_id=school.pk, user_id=uid).exists():
        return None
    return email


def render_notification_intent(
    *,
    template_key: str,
    locale: str = "en",
    context: Optional[dict[str, Any]] = None,
) -> tuple[str, str, Optional[str]]:
    """Return (subject, text_body, html_body)."""
    ctx = context or {}
    locale_code = (locale or "en").strip().lower()[:8] or "en"
    if template_key == "low_meal_balance":
        student = ctx.get("student_name") or "your student"
        subject = "Meal plan balance notice"
        body = f"Hello — this is a notice regarding meal plan balance for {student}."
        return subject, body, None
    if template_key == "exam_readiness":
        subject = "Exam readiness update"
        body = "Hello — your student's exam readiness information is available in the portal."
        return subject, body, None
    # Additional templates use honest minimal copy until locale files wire in.
    subject = f"School notification ({template_key})"
    body = f"Hello — you have a new school notification ({template_key})."
    return subject, body, None


def dispatch_notification_intent(
    *,
    school,
    action_type: str,
    payload: dict[str, Any],
    idempotency_key: str = "",
    async_send: bool = True,
) -> dict[str, Any]:
    """Resolve recipient from DB, render template, send via send_transactional."""
    errors = validate_offline_payload(action_type, payload)
    if errors:
        return {"ok": False, "error": "; ".join(errors), "queued": False}

    recipient_id = str(
        payload.get("recipient_user_id") or payload.get("recipient_id") or ""
    ).strip()
    template_key = (payload.get("template_key") or "").strip()
    locale = (payload.get("locale") or payload.get("context", {}).get("locale") or "en")
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    to_email = _resolve_recipient_email(school=school, recipient_user_id=recipient_id)
    if not to_email:
        return {"ok": False, "error": "recipient_not_found", "queued": False}

    subject, body, html_body = render_notification_intent(
        template_key=template_key,
        locale=locale,
        context=context,
    )
    idem = (idempotency_key or "").strip()[:128]
    tenant_hash = _hash_tenant(school.pk)

    if async_send:
        try:
            from apps.schoolops.tasks import deliver_notification_intent_task

            deliver_notification_intent_task.delay(
                school_id=school.pk,
                subject=subject,
                body=body,
                to_hash_target=hashlib.sha256(to_email.encode()).hexdigest()[:12],
                to_email=to_email,
                html_body=html_body,
                idempotency_key=idem,
                tenant_hash=tenant_hash,
            )
            return {"ok": True, "queued": True, "delivery_id": idem or None}
        except Exception as exc:
            logger.warning(
                "notification_intent.celery_unavailable err_type=%s tenant_hash=%s",
                type(exc).__name__,
                tenant_hash,
            )

    from apps.schoolops.email_delivery import send_transactional

    result = send_transactional(
        subject=subject,
        body=body,
        to=to_email,
        html_body=html_body,
        async_send=False,
        tenant_hash=tenant_hash,
        school=school,
        idempotency_key=idem,
    )
    result["queued"] = bool(result.get("queued"))
    return result


__all__ = [
    "dispatch_notification_intent",
    "render_notification_intent",
]
