"""Delivery-channel readiness diagnostics (LOW-9).

Operators had no single place to answer "is browser web push actually configured
on this deployment?" — the VAPID keys live in settings, the subscriptions in a
table, and nothing surfaced whether the two lined up. (Web push itself IS wired
into the dispatch router — :func:`apps.communication.dispatch._send_push` fans to
both native FCM/APNS and browser web push — so this closes the *visibility* gap,
not a delivery gap.)

:func:`collect_delivery_health` returns a readiness snapshot per channel. It
reports **booleans and counts only — never key material** — and every probe is
failure-isolated, so a missing setting or un-provisioned table yields ``False`` /
``None`` instead of raising. Safe to call from any operator-gated surface.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _email_health() -> dict:
    backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")
    short = backend.rsplit(".", 1)[-1] if backend else ""
    host = str(getattr(settings, "EMAIL_HOST", "") or "")
    # A dev/test backend (console/locmem/filebased) needs no host to be "ready".
    dev_backend = any(t in backend for t in ("console", "locmem", "filebased"))
    return {
        "backend": short,
        "host_configured": bool(host),
        "configured": bool(host) or dev_backend,
    }


def _sms_health() -> dict:
    # Best-effort: a provider is "configured" if any known credential is present.
    candidates = (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "AFRICASTALKING_API_KEY",
        "AFRICASTALKING_USERNAME",
    )
    configured = any(bool(getattr(settings, name, "")) for name in candidates)
    return {"provider_configured": configured}


def _web_push_health() -> dict:
    info = {
        "vapid_configured": False,
        "public_key_present": False,
        "active_subscribers": None,
    }
    try:
        from apps.communication import web_push_service

        info["vapid_configured"] = bool(web_push_service.vapid_configured())
        info["public_key_present"] = bool(web_push_service.vapid_public_key())
    except Exception as exc:  # noqa: BLE001 — diagnostic must never raise
        logger.debug(
            "delivery health: web push introspect failed err=%s", type(exc).__name__
        )
    try:
        from apps.communication.models_web_push import WebPushSubscription

        # tenant-isolation-allow: platform-readiness-count-not-tenant-scoped-data
        info["active_subscribers"] = WebPushSubscription.objects.filter(
            is_active=True
        ).count()
    except Exception:  # noqa: BLE001 — table may not exist on this host
        info["active_subscribers"] = None
    return info


def _native_push_health() -> dict:
    fcm = str(
        getattr(settings, "FCM_SERVER_KEY", "")
        or getattr(settings, "FIREBASE_SERVER_KEY", "")
        or ""
    )
    info = {"fcm_configured": bool(fcm), "active_devices": None}
    try:
        from apps.api.mobile_api import MobileDevice

        # tenant-isolation-allow: platform-readiness-count-not-tenant-scoped-data
        info["active_devices"] = (
            MobileDevice.objects.filter(is_active=True).exclude(push_token="").count()
        )
    except Exception:  # noqa: BLE001 — table may not exist on this host
        info["active_devices"] = None
    return info


def collect_delivery_health() -> dict:
    """Return a per-channel readiness snapshot (booleans + counts, no secrets).

    Keys: ``email`` / ``sms`` / ``web_push`` / ``native_push``. Each probe is
    independently failure-isolated.
    """
    return {
        "email": _email_health(),
        "sms": _sms_health(),
        "web_push": _web_push_health(),
        "native_push": _native_push_health(),
    }


__all__ = ["collect_delivery_health"]
