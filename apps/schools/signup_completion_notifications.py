"""Signup completion emails and portal-ready notifications (2026-06-08).

Platform-wide contract for every tenant: verify → provision → portal-ready
comms (email, inbox, SMS, web push) + first-login corner nudge. Not scoped to
individual incident schools.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

SETTINGS_KEY = "signup_notifications"
_COMPLETION_SUBJECT_SNIPPET = "Welcome to RunMyCampus"


def _notification_state(school) -> dict:
    settings_blob = dict(getattr(school, "settings", None) or {})
    state = dict(settings_blob.get(SETTINGS_KEY) or {})
    return state


def _save_notification_state(school, state: dict) -> None:
    if not school or not getattr(school, "pk", None):
        return
    settings_blob = dict(getattr(school, "settings", None) or {})
    settings_blob[SETTINGS_KEY] = state
    school.settings = settings_blob
    try:
        school.save(update_fields=["settings", "updated_at"])
    except Exception:  # noqa: BLE001 — notification stamp is best-effort
        logger.warning("signup_notification_state_save_failed", exc_info=True)


def _mark_notification_sent(
    school,
    *,
    event: str,
    delivery_event_id: str = "",
    delivered: bool = False,
) -> None:
    from django.utils import timezone

    state = _notification_state(school)
    now_iso = timezone.now().isoformat()
    state[f"{event}_at"] = now_iso
    state[f"{event}_dispatched_at"] = now_iso
    if delivered:
        state[f"{event}_delivered_at"] = now_iso
        if delivery_event_id:
            state["completion_delivery_event_id"] = delivery_event_id[:64]
    _save_notification_state(school, state)


def signup_completion_was_delivered(school) -> bool:
    state = _notification_state(school)
    if state.get("completed_delivered_at"):
        return True
    # Legacy rows only stamped completed_at before delivery-aware idempotency.
    return bool(state.get("completed_at") and state.get("completion_delivery_event_id"))


def _confirm_completion_delivery(contact_email: str, *, window_seconds: int = 180) -> dict:
    """Return the latest successful EmailDeliveryEvent for a completion mail."""
    email = (contact_email or "").strip()
    if not email:
        return {}
    try:
        from django.utils import timezone

        from apps.schoolops.email_delivery import _hash_recipient
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent
    except ImportError:
        return {}

    cutoff = timezone.now() - timezone.timedelta(seconds=window_seconds)
    to_hash = _hash_recipient(email)
    try:
        rows = (
            EmailDeliveryEvent.objects.filter(
                to_hash=to_hash,
                created_at__gte=cutoff,
                ok=True,
            )
            .order_by("-created_at")
            .values("id", "subject_prefix", "idempotency_key")[:12]
        )
    except Exception:  # noqa: BLE001
        return {}

    for row in rows:
        subject = (row.get("subject_prefix") or "").strip()
        idem = (row.get("idempotency_key") or "").strip()
        if _COMPLETION_SUBJECT_SNIPPET in subject or "tenant.signup.completed" in idem:
            return {
                "delivery_event_id": str(row.get("id") or ""),
                "ok": True,
            }
    return {}


def _resolve_admin_user(school, contact_email: str):
    from django.contrib.auth import get_user_model

    from apps.schools.models import SchoolMembership

    User = get_user_model()
    email = (contact_email or "").strip()
    if email:
        user = User.objects.filter(email__iexact=email).order_by("pk").first()
        if user:
            return user
    membership = (
        SchoolMembership.objects.filter(school=school, is_primary=True)
        .select_related("user")
        .order_by("id")
        .first()
        or SchoolMembership.objects.filter(school=school)
        .select_related("user")
        .order_by("id")
        .first()
    )
    return membership.user if membership else None


def build_signup_completed_payload(
    school, contact_email: str, admin_user=None
) -> dict[str, Any]:
    """Matrix payload for tenant.signup.completed — password-aware."""
    from apps.schools.provision_email_urls import (
        build_owner_onboarding_url,
        build_provision_setup_password_url,
        build_public_login_url,
        build_tenant_authentication_url,
        build_tenant_workspace_login_url,
        tenant_subdomain_host_exists,
    )

    admin_user = admin_user or _resolve_admin_user(school, contact_email)
    tenant_portal_url = build_tenant_authentication_url(
        school, "/authentication/login/"
    )
    portal_url = (
        build_tenant_workspace_login_url(school)
        if tenant_subdomain_host_exists(school)
        else build_public_login_url()
    )
    activation_url = ""
    account_ready = bool(
        admin_user
        and getattr(admin_user, "has_usable_password", None)
        and admin_user.has_usable_password()
    )
    if admin_user and not account_ready:
        activation_url = build_owner_onboarding_url(school, admin_user) or ""
        if not activation_url:
            activation_url = build_provision_setup_password_url(
                school, admin_user
            ) or ""
    return {
        "school_id": str(getattr(school, "pk", "") or ""),
        "school_name": getattr(school, "name", "") or "",
        "admin_email": (contact_email or "").strip(),
        "portal_url": portal_url,
        "tenant_portal_url": tenant_portal_url,
        "activation_url": activation_url,
        "account_ready": account_ready,
        "subdomain": (
            getattr(school, "subdomain", None)
            or getattr(school, "slug", None)
            or ""
        ),
    }


def notify_tenant_signup_completed(
    school,
    contact_email: str,
    *,
    admin_user=None,
    force: bool = False,
) -> bool:
    """
    Idempotent portal-ready email after ``school.is_active`` is True.

    Skips when ``completed_delivered_at`` is set unless ``force=True``.
    Returns True when SMTP delivery is confirmed or welcome fallback succeeds.
    """
    if not school or not getattr(school, "is_active", False):
        return False
    email = (contact_email or "").strip()
    if not email:
        return False

    state = _notification_state(school)
    if state.get("completed_delivered_at") and not force:
        return True
    if state.get("completed_dispatched_at") and not force:
        return True

    if force:
        state.pop("completed_at", None)
        state.pop("completed_dispatched_at", None)
        state.pop("completed_delivered_at", None)
        state.pop("completion_delivery_event_id", None)
        for channel_key in (
            "in_app_dispatched_at",
            "sms_dispatched_at",
            "web_push_dispatched_at",
        ):
            state.pop(channel_key, None)
        _save_notification_state(school, state)

    admin_user = admin_user or _resolve_admin_user(school, email)
    payload = build_signup_completed_payload(school, email, admin_user=admin_user)
    dispatched = False
    try:
        from apps.platform_runtime.event_bus import publish_event

        row = publish_event(
            "tenant.signup.completed",
            payload,
            school_id=str(school.pk),
            strict_catalog=True,
            source="schools.signup_completion_notifications",
            idempotency_key=f"tenant-signup-completed:{school.pk}",
        )
        dispatched = row is not None
    except (
        ImportError,
        AttributeError,
        TypeError,
        ValueError,
        OSError,
        RuntimeError,
    ) as exc:
        logger.warning(
            "tenant.signup.completed publish failed school=%s: %s",
            getattr(school, "pk", None),
            type(exc).__name__,
        )

    delivery = _confirm_completion_delivery(email)
    delivered = bool(delivery.get("ok"))
    if not delivered and not dispatched:
        try:
            from apps.schools.welcome_email import send_welcome_email

            delivered = bool(send_welcome_email(str(school.pk), email))
            if delivered:
                delivery = _confirm_completion_delivery(email) or {"ok": True}
        except Exception:  # noqa: BLE001
            logger.warning("welcome_email_fallback_failed", exc_info=True)

    if dispatched or delivered:
        _mark_notification_sent(
            school,
            event="completed",
            delivery_event_id=str(delivery.get("delivery_event_id") or ""),
            delivered=delivered,
        )
        try:
            from apps.schools.signup_portal_channel_notifications import (
                dispatch_portal_ready_channels,
            )

            dispatch_portal_ready_channels(
                school,
                email,
                payload,
                admin_user=admin_user,
                force=force,
            )
        except Exception:  # noqa: BLE001 — channels are best-effort
            logger.warning("portal_ready_channel_dispatch_failed", exc_info=True)
    return delivered or dispatched


def notify_provisioning_failed_operator(school, contact_email: str, *, error: str = "") -> None:
    """Best-effort operator alert when provisioning fails after signup verify."""
    if not school:
        return
    payload = {
        "school_id": str(getattr(school, "pk", "") or ""),
        "school_name": getattr(school, "name", "") or "",
        "slug": getattr(school, "slug", "") or "",
        "admin_email": (contact_email or "").strip(),
        "error_summary": (error or "unknown")[:500],
    }
    try:
        from apps.platform_runtime.event_bus import publish_event

        publish_event(
            "tenant.signup.provisioning_failed",
            payload,
            school_id=str(school.pk),
            strict_catalog=False,
            source="schools.signup_completion_notifications",
            idempotency_key=f"tenant-signup-provision-failed:{school.pk}",
        )
    except (
        ImportError,
        AttributeError,
        TypeError,
        ValueError,
        OSError,
        RuntimeError,
    ):
        logger.warning("provisioning_failed_operator_alert_skipped", exc_info=True)


def finalize_tenant_activation(school, contact_email: str = "", **kwargs) -> None:
    """
    Post-activate hook: sync domains to runtime + send portal-ready comms.
    """
    if not school or not getattr(school, "is_active", False):
        return
    try:
        from apps.schools.domain_sync import sync_school_domains_to_runtime

        sync_school_domains_to_runtime(school)
    except (
        OSError,
        ConnectionError,
        ImportError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        logger.warning(
            "post_activate_domain_sync_failed school=%s",
            getattr(school, "pk", None),
            exc_info=True,
        )
    notify_tenant_signup_completed(
        school,
        contact_email,
        admin_user=kwargs.get("admin_user"),
    )
