"""In-app inbox + SMS portal-ready channels for signup completion (2026-06-08)."""

from __future__ import annotations

import logging
from typing import Any

from django.utils.translation import gettext as _

from apps.schools.signup_completion_notifications import (
    _notification_state,
    _resolve_admin_user,
    _save_notification_state,
)

logger = logging.getLogger(__name__)

PORTAL_READY_INBOX_TITLE = "Your RunMyCampus portal is ready"


def _resolve_owner_phone(user, school) -> str:
    """Best-effort phone for SMS; signup may not capture one yet."""
    if user:
        for attr in ("phone", "phone_number", "mobile", "mobile_phone"):
            val = getattr(user, attr, None)
            if val and str(val).strip():
                return str(val).strip()
    settings_blob = dict(getattr(school, "settings", None) or {})
    for key in ("contact_phone", "admin_phone", "phone"):
        val = settings_blob.get(key) or ""
        if str(val).strip():
            return str(val).strip()
    rmc = dict(settings_blob.get("rmc_public_onboarding") or {})
    for key in ("phone", "contact_phone", "admin_phone"):
        val = rmc.get(key) or ""
        if str(val).strip():
            return str(val).strip()
    return ""


def _portal_ready_link(payload: dict[str, Any]) -> str:
    link = (payload.get("activation_url") or payload.get("portal_url") or "").strip()
    return link[:256]


def _build_portal_ready_sms_body(payload: dict[str, Any]) -> str:
    name = ((payload.get("school_name") or "Your school") or "")[:40]
    url = (payload.get("activation_url") or payload.get("portal_url") or "").strip()
    if url:
        return f"RunMyCampus: {name} is ready. Sign in: {url[:90]}"
    return f"RunMyCampus: {name} is ready. Check your email to sign in."


def _mark_channel_sent(school, channel: str) -> None:
    from django.utils import timezone

    state = _notification_state(school)
    now_iso = timezone.now().isoformat()
    state[f"{channel}_dispatched_at"] = now_iso
    _save_notification_state(school, state)


def ensure_portal_ready_in_app_notification(
    admin_user,
    school,
    payload: dict[str, Any],
    *,
    force: bool = False,
):
    """Create finance.Notification inbox row for the school owner."""
    if not admin_user or not getattr(admin_user, "pk", None) or not school:
        return None

    state = _notification_state(school)
    if state.get("in_app_dispatched_at") and not force:
        try:
            from apps.finance.models import Notification

            return (
                # tenant-isolation-allow: recipient-scoped-school-owner-owns-notification
                Notification.objects.filter(
                    recipient=admin_user,
                    title=PORTAL_READY_INBOX_TITLE,
                )
                .order_by("-created_at")
                .first()
            )
        except Exception:  # noqa: BLE001
            return None

    try:
        from apps.finance.models import Notification

        if not force:
            existing = (
                # tenant-isolation-allow: recipient-scoped-school-owner-owns-notification
                Notification.objects.filter(
                    recipient=admin_user,
                    title=PORTAL_READY_INBOX_TITLE,
                    is_read=False,
                )
                .order_by("-created_at")
                .first()
            )
            if existing:
                _mark_channel_sent(school, "in_app")
                return existing

        school_name = payload.get("school_name") or getattr(school, "name", "")
        if payload.get("account_ready"):
            message = _(
                "Your school %(name)s is live. Sign in to open your portal."
            ) % {"name": school_name}
        else:
            message = _(
                "Your school %(name)s is ready. Set your password to sign in."
            ) % {"name": school_name}

        note = Notification.objects.create(
            recipient=admin_user,
            title=PORTAL_READY_INBOX_TITLE,
            message=message,
            link=_portal_ready_link(payload),
            severity=Notification.Severity.INFO,
            created_by=None,
        )
        _mark_channel_sent(school, "in_app")
        return note
    except Exception:  # noqa: BLE001 — inbox row must not break email path
        logger.warning("portal_ready_in_app_notification_failed", exc_info=True)
        return None


def notify_portal_ready_sms(
    admin_user,
    school,
    payload: dict[str, Any],
    contact_email: str = "",
    *,
    force: bool = False,
) -> bool:
    """Best-effort SMS when owner phone is known; falls back to email on failure."""
    if not school:
        return False

    state = _notification_state(school)
    if state.get("sms_dispatched_at") and not force:
        return False

    phone = _resolve_owner_phone(admin_user, school)
    if not phone:
        return False

    body = _build_portal_ready_sms_body(payload)
    email = (contact_email or "").strip()
    idempotency_key = f"tenant-signup-portal-sms:{getattr(school, 'pk', '')}"

    try:
        from apps.communication.notification_service import send_sms

        ok = send_sms(
            phone,
            body,
            school=school,
            fallback_email=email or None,
            idempotency_key=idempotency_key,
        )
        if ok:
            _mark_channel_sent(school, "sms")
        return ok
    except Exception:  # noqa: BLE001
        logger.warning("portal_ready_sms_failed", exc_info=True)
        return False


def notify_portal_ready_web_push(
    admin_user,
    school,
    payload: dict[str, Any],
    *,
    force: bool = False,
) -> int:
    """Browser push when the owner already subscribed on a prior session."""
    if not admin_user or not school:
        return 0

    state = _notification_state(school)
    if state.get("web_push_dispatched_at") and not force:
        return 0

    school_name = payload.get("school_name") or getattr(school, "name", "")
    if payload.get("account_ready"):
        body = _("Your school %(name)s is live. Tap to open your portal.") % {
            "name": school_name
        }
    else:
        body = _("Your school %(name)s is ready. Tap to set your password.") % {
            "name": school_name
        }
    url = _portal_ready_link(payload)

    try:
        from apps.communication.web_push_service import send_web_push_to_user

        sent = send_web_push_to_user(
            admin_user,
            title=PORTAL_READY_INBOX_TITLE,
            body=body,
            url=url,
            tag=f"portal-ready:{getattr(school, 'pk', '')}",
        )
        if sent:
            _mark_channel_sent(school, "web_push")
        return sent
    except Exception:  # noqa: BLE001
        logger.warning("portal_ready_web_push_failed", exc_info=True)
        return 0


def dispatch_portal_ready_channels(
    school,
    contact_email: str,
    payload: dict[str, Any],
    *,
    admin_user=None,
    force: bool = False,
) -> None:
    """In-app inbox + SMS after portal-ready email/matrix dispatch."""
    admin_user = admin_user or _resolve_admin_user(school, contact_email)
    if not admin_user:
        return
    ensure_portal_ready_in_app_notification(
        admin_user, school, payload, force=force
    )
    notify_portal_ready_sms(
        admin_user,
        school,
        payload,
        contact_email,
        force=force,
    )
    notify_portal_ready_web_push(
        admin_user,
        school,
        payload,
        force=force,
    )
