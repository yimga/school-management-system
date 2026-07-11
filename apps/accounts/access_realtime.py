"""Real-time fan-out for a user's RBAC / authority changes.

Server-side, a change to a user's authority already takes effect on their NEXT
request — ``User.has_feature_permission`` reads the grants live every request, and
there is no per-user permission cache. This module is the producer half of the
real-time rail that closes the "already-open browser shows stale nav" gap: when a
user's Django flags (``is_superuser``/``is_staff``), primary ``role``, granular
AccessRole grants (``user.roles``), or direct ``feature_permissions`` change, it
pushes an ``access_changed`` event to that user's OWN per-(school, user) Channels
rooms so ``apps.api.consumers.NotificationSyncConsumer`` delivers it live and the
client refreshes nav / permissions.

Mirrors ``apps/finance/notification_realtime.py`` (same room formula, same
tenant-isolation + fail-soft guarantees) — no new socket protocol is invented.
The room name is reused verbatim via ``notification_room_name`` so a push lands in
the exact room the user's notification socket already joined.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _user_school_ids(user: Any) -> list:
    """School ids the user belongs to — the rooms to fan an access change out to.

    Best-effort: a lookup error yields an empty list (no push), never an exception.
    """
    try:
        # tenant-isolation-allow: school-membership-is-per-user-identity-lookup
        return list(user.school_memberships.values_list("school_id", flat=True))
    except Exception:  # noqa: BLE001 — membership lookup is best-effort
        return []


def push_access_changed_realtime(user: Any, *, reason: str = "") -> int:
    """Best-effort live-push of an access change to the user's own rooms.

    Sends ``{"type": "access.changed"}`` to ``notifications_sync_{school}_{user}``
    for every school the user belongs to — the exact rooms that user's own
    ``NotificationSyncConsumer`` sockets joined — so a push can never reach another
    user or cross a tenant boundary. Returns the number of rooms a ``group_send``
    was issued to (0 when skipped). Never raises: an authority write must succeed
    regardless of the socket layer.
    """
    user_id = getattr(user, "pk", None)
    if not user_id:
        return 0
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from apps.finance.notification_realtime import notification_room_name

        layer = get_channel_layer()
        if layer is None:
            return 0
        sent = 0
        for school_id in _user_school_ids(user):
            if not school_id:
                continue
            async_to_sync(layer.group_send)(
                notification_room_name(school_id, user_id),
                {"type": "access.changed", "reason": reason},
            )
            sent += 1
        return sent
    except Exception as exc:  # noqa: BLE001 — real-time layer is best-effort
        logger.debug("access-changed realtime push skipped: %s", exc)
        return 0
