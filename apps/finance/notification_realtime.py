"""Real-time fan-out for persisted notifications.

The bell badge historically only POLLED ``apps.api.notification_api`` for the
unread count, so a people-domain notification (attendance / discipline / eval /
badge-expiry / finance) reached the recipient only on their next page load. This
module is the producer half of a real-time rail: when the canonical
``finance.NotificationManager.notify_unread`` write path persists a
:class:`apps.finance.models.Notification`, the freshly written row is also pushed
to the recipient's tenant-scoped Channels group so
``apps.api.consumers.NotificationSyncConsumer`` delivers it live.

Design constraints (mirrors ``apps/schoolops/substitute_market.py`` +
``apps/api/consumers.py`` — no new socket protocol is invented):

* The group name is byte-identical to
  ``tenant_sync_room_name("notifications_sync", scope)``
  (apps/schools/channels_tenant_middleware.py), so the producer's ``group_send``
  lands in the exact room the consumer joined. Locked by
  ``test_notification_realtime_fanout.test_room_formula_matches_consumer``.
* A notification is fanned out only when it carries BOTH a ``school`` and a
  ``recipient``. A null-school (platform/global) or null-recipient row is never
  broadcast, so a live push can never cross a tenant boundary.
* The recipient's in-app preference is honored: a user whose
  ``UserPreference.notification_channels`` is an explicit list that excludes
  ``APP`` has opted out of live in-app delivery and is not pushed (the row still
  persists and shows in their inbox on next load).
* Fail-soft: any Channels/preference error is swallowed (the real-time layer is
  best-effort) and never breaks the DB write. PII in the payload
  (title / message) is never logged.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# UserPreference.NotificationChannel.APP — the in-app / live-push channel token.
_APP_CHANNEL = "APP"


def notification_room_name(school_id: Any, user_id: Any) -> str:
    """Tenant-scoped Channels group for one (school, recipient).

    Must stay byte-identical to
    ``tenant_sync_room_name("notifications_sync", scope)``
    (apps/schools/channels_tenant_middleware.py) so a producer send reaches the
    room ``NotificationSyncConsumer`` is listening on.
    """
    return f"notifications_sync_{school_id}_{user_id}"


def wants_realtime_notification(user_id: Any) -> bool:
    """True unless the recipient has explicitly opted OUT of in-app delivery.

    Opt-out semantics (matches the notification-preferences UI where a user picks
    an explicit channel set): a user whose ``UserPreference.notification_channels``
    is a NON-empty list that does not include ``APP`` has deselected in-app
    notifications, so there is no live push. No preference row, an empty/unset
    list, or a list including ``APP`` -> delivered. Fail-open (deliver) on any
    lookup error — the persisted inbox row is the source of truth regardless.
    """
    try:
        from apps.siteconfig.models_tooling import UserPreference

        # tenant-isolation-allow: user-preference-is-per-user-identity-not-school-scoped
        channels = (
            UserPreference.objects.filter(user_id=user_id)
            .values_list("notification_channels", flat=True)
            .first()
        )
    except Exception:  # noqa: BLE001 — preference is best-effort; deliver on error
        return True
    if not channels:
        return True
    return _APP_CHANNEL in {str(c).upper() for c in channels}


def build_notification_payload(notification) -> dict[str, Any]:
    """Compact client-facing shape (mirrors ``notification_api.list`` rows)."""
    created = getattr(notification, "created_at", None)
    return {
        "id": getattr(notification, "id", None),
        "title": getattr(notification, "title", "") or "",
        "message": getattr(notification, "message", "") or "",
        "severity": getattr(notification, "severity", "") or "",
        "link": getattr(notification, "link", "") or "",
        "is_read": bool(getattr(notification, "is_read", False)),
        "created_at": created.isoformat() if created else None,
    }


def push_notification_realtime(notification) -> bool:
    """Best-effort live-push of a persisted notification to its recipient.

    Returns ``True`` when a ``group_send`` was issued, ``False`` when skipped
    (no school/recipient, opted-out, or no channel layer configured). Never
    raises — the DB write must succeed regardless of the socket layer.
    """
    school_id = getattr(notification, "school_id", None)
    recipient_id = getattr(notification, "recipient_id", None)
    if not school_id or not recipient_id:
        return False
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return False
        if not wants_realtime_notification(recipient_id):
            return False
        async_to_sync(layer.group_send)(
            notification_room_name(school_id, recipient_id),
            {
                "type": "notification.message",
                "notification": build_notification_payload(notification),
            },
        )
        return True
    except Exception as exc:  # noqa: BLE001 — real-time layer is best-effort
        logger.debug("notification realtime push skipped: %s", exc)
        return False
