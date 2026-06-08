"""Web Push (VAPID) subscribe + send helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def vapid_public_key() -> str:
    return (getattr(settings, "WEB_PUSH_VAPID_PUBLIC_KEY", "") or "").strip()


def vapid_configured() -> bool:
    private_key = (getattr(settings, "WEB_PUSH_VAPID_PRIVATE_KEY", "") or "").strip()
    return bool(vapid_public_key() and private_key)


def vapid_claims_email() -> str:
    return (
        getattr(settings, "WEB_PUSH_VAPID_CLAIMS_EMAIL", "")
        or "mailto:noreply@runmycampus.com"
    ).strip()


def upsert_web_push_subscription(user, payload: dict[str, Any]):
    """Persist Push API subscription JSON from the browser."""
    from apps.communication.models_web_push import WebPushSubscription

    endpoint = (payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return None
    row, _created = WebPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": user,
            "p256dh": p256dh,
            "auth": auth,
            "is_active": True,
        },
    )
    return row


def deactivate_web_push_subscription(user, endpoint: str) -> None:
    from apps.communication.models_web_push import WebPushSubscription

    endpoint = (endpoint or "").strip()
    if not endpoint:
        return
    WebPushSubscription.objects.filter(user=user, endpoint=endpoint).update(
        is_active=False
    )


def send_web_push(
    subscription_row,
    *,
    title: str,
    body: str,
    url: str = "",
    tag: str = "rmc-portal-ready",
) -> bool:
    """Deliver one browser push notification; deactivates expired endpoints."""
    if not vapid_configured():
        return False
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("web_push_send_skipped_pywebpush_missing")
        return False

    payload = json.dumps(
        {
            "title": (title or "RunMyCampus")[:120],
            "body": (body or "")[:240],
            "url": (url or "")[:512],
            "tag": (tag or "rmc-push")[:64],
        }
    )
    try:
        webpush(
            subscription_info=subscription_row.subscription_info(),
            data=payload,
            vapid_private_key=getattr(settings, "WEB_PUSH_VAPID_PRIVATE_KEY", ""),
            vapid_claims={"sub": vapid_claims_email()},
        )
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            subscription_row.is_active = False
            subscription_row.save(update_fields=["is_active", "updated_at"])
        logger.info(
            "web_push_send_failed status=%s endpoint=%s",
            status,
            str(subscription_row.endpoint)[:48],
        )
        return False
    except (OSError, ConnectionError, TimeoutError, TypeError, ValueError) as exc:
        logger.warning("web_push_send_failed err=%s", type(exc).__name__)
        return False


def send_web_push_to_user(
    user,
    *,
    title: str,
    body: str,
    url: str = "",
    tag: str = "rmc-portal-ready",
) -> int:
    """Fan-out to all active browser subscriptions for a user."""
    if not user or not getattr(user, "pk", None) or not vapid_configured():
        return 0
    from apps.communication.models_web_push import WebPushSubscription

    sent = 0
    for row in WebPushSubscription.objects.filter(user=user, is_active=True):
        if send_web_push(row, title=title, body=body, url=url, tag=tag):
            sent += 1
    return sent
