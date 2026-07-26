"""Server-owned notification intents — never client SMTP (SODP batch 1407)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from django.contrib.auth import get_user_model

from apps.platform_runtime.offline_action_types import validate_offline_payload

logger = logging.getLogger(__name__)


def _ctx_currency(ctx: dict[str, Any]) -> str:
    """Local-first fallback currency for a notification body when the caller
    omits one: the context school's ``resolve_currency()`` cascade -> platform
    default. Never blank — so a body never reads "Amount: 50 ." with a bare
    number and no currency for a non-USD school.
    """
    from django.conf import settings

    school = ctx.get("school")
    if school is not None:
        try:
            code = (school.resolve_currency() or "").strip()
            if code:
                return code.upper()
        except Exception:  # noqa: BLE001 — never break a notification on currency lookup
            pass
    return (getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD") or "USD").upper()


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


def _inline_notification(template_key: str, ctx: dict[str, Any]) -> tuple[str, str]:
    """English inline (subject, body) used when no localized template ships for
    this ``template_key`` — the deterministic fallback for
    :func:`render_notification_intent`."""
    if template_key == "low_meal_balance":
        student = ctx.get("student_name") or "your student"
        return (
            "Meal plan balance notice",
            f"Hello — this is a notice regarding meal plan balance for {student}.",
        )
    if template_key == "exam_readiness":
        return (
            "Exam readiness update",
            "Hello — your student's exam readiness information is available in the portal.",
        )
    if template_key == "fee_reminder":
        return (
            "Fee payment reminder",
            "Hello — this is a reminder about an outstanding school fee balance. "
            "Sign in to the parent portal for details and payment options.",
        )
    if template_key == "payment_received":
        student = ctx.get("student_name") or "your student"
        amount = ctx.get("amount") or ""
        currency = ctx.get("currency") or _ctx_currency(ctx)
        reference = ctx.get("reference") or ""
        return (
            "Payment received",
            f"Hello — we recorded a payment for {student}. "
            f"Amount: {amount} {currency}. Reference: {reference}. "
            "Sign in to the parent portal for your receipt.",
        )
    if template_key == "transport_delay":
        route = ctx.get("route_name") or "your student's route"
        return (
            "Transport update",
            f"Hello — there is a transport schedule update for {route}. "
            "Open the portal for the latest arrival or pickup information.",
        )
    if template_key == "wellbeing_checkin":
        return (
            "Wellbeing check-in",
            "Hello — your school has shared a wellbeing check-in update. "
            "Please review the message in the parent portal when you can.",
        )
    return (
        f"School notification ({template_key})",
        f"Hello — you have a new school notification ({template_key}).",
    )


def render_notification_intent(
    *,
    template_key: str,
    locale: str = "en",
    context: Optional[dict[str, Any]] = None,
) -> tuple[str, str, Optional[str]]:
    """Return (subject, text_body, html_body).

    Prefers the shared locale-aware email templates
    (``schoolops/email/locale/<code>/<template_key>.{txt,html}``) so a non-English
    recipient gets the translated body that already ships on disk — the SAME
    renderer the primary low-meal-balance path uses (``schoolops.tasks``). Before
    this, every ``notify.*`` intent rendered a hardcoded English one-liner and the
    ``locale`` argument was dead, so a French/Arabic parent got English even though
    the translated copy existed. ``render_localized_email`` owns the locale →
    ``en`` → legacy cascade and raises ``TemplateDoesNotExist`` only when NO
    template exists for this key at all — that is the signal to fall back to the
    English inline body. Dropping in a new ``locale/<code>/<key>`` template
    localizes this path with no code change (GAP-5 contract). The subject stays
    inline English: the templates carry no subject line, which also matches the
    primary path's English subject alongside a localized body.
    """
    ctx = context or {}
    subject, inline_body = _inline_notification(template_key, ctx)

    from django.template import TemplateDoesNotExist

    from apps.communication.email_locale import render_localized_email

    try:
        rendered = render_localized_email(
            "schoolops/email", template_key, locale, ctx
        )
    except TemplateDoesNotExist:
        return subject, inline_body, None
    return subject, rendered.text, rendered.html


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

    from apps.schoolops.email_delivery import send_transactional

    # ``async_send`` now uses the IN-PROCESS daemon-thread sender
    # (send_transactional async_send=True) rather than a Celery task. On the
    # free tier the Celery worker is a separate, frequently-asleep service, so a
    # successful ``.delay()`` returned ``queued=True`` while the message sat in
    # the queue undelivered (H3). The daemon thread runs inside this process —
    # the same proven path as signup activation — so delivery never depends on
    # the worker being awake. (Trade-off: no offload to a worker process; fine
    # for transactional email volume.)
    result = send_transactional(
        subject=subject,
        body=body,
        to=to_email,
        html_body=html_body,
        async_send=bool(async_send),
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
