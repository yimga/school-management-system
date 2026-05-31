"""v4.00.91 Wave B — default badge resolvers for the six v1 chips.

Real resolvers ship for ``messages`` (unread count from communication app
when present) + ``ai-copilot`` (count of pending proactive insights —
honest stub returning None until Wave D wires it). The remaining chips
keep no default badge (resolver returns None) so the JS doesn't paint a
pill unnecessarily.
"""

from __future__ import annotations

import logging

from .badges import (
    BADGE_LEVEL_INFO,
    BADGE_LEVEL_SUCCESS,
    BadgeSnapshot,
    register_badge_resolver,
)

logger = logging.getLogger(__name__)


def _user_school(request):
    """Return the resolved tenant School or None — used to scope queries."""
    return getattr(request, "school", None) or getattr(request, "tenant", None)


def messages_badge_resolver(request, *, slot, page_path):  # noqa: ARG001 — interface
    """Unread message count for the active user, capped at 99+.

    Returns None when the communication app, the user, or the recipient
    table is unavailable — the dock simply paints no badge in those cases.
    Tenant-scoped via the standard request.user filter.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    try:
        # apps.communication.Message has a recipient + is_read FK pattern
        # across most surfaces; if the schema differs, the import error
        # path returns None cleanly.
        from apps.communication.models import Message  # type: ignore
    except (ImportError, RuntimeError):
        return None
    try:
        # tenant-isolation-allow: assist-dock-messages-badge-user-scoped-recipient
        unread = Message.objects.filter(
            recipient=user, is_read=False
        ).count()
    except (AttributeError, RuntimeError, TypeError, ValueError):
        # Includes TypeError so mocked / non-ORM-shaped Message objects in
        # tests + transient schema mismatches in production both no-op.
        return None
    if not unread:
        return None
    return BadgeSnapshot(
        count=min(unread, 99),
        dot=True,
        level=BADGE_LEVEL_INFO,
        tooltip=f"{unread} unread message(s)",
    )


def ai_copilot_badge_resolver(request, *, slot, page_path):  # noqa: ARG001
    """Proactive copilot insight count.

    Wave D: reads the in-process insights ring keyed by user_id and
    filtered to ``page_path``. Returns None when nothing is pending so
    the dock paints no pill (rather than a noisy ``0``).
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    user_id = getattr(user, "pk", None)
    if not user_id:
        return None
    try:
        from .insights import (
            INSIGHT_CRITICAL,
            INSIGHT_WARNING,
            list_insights,
        )
    except (ImportError, RuntimeError):
        return None
    items = list_insights(user_id, page_path=page_path)
    if not items:
        return None
    # Promote pill level to the most severe insight currently pending.
    levels = {i.level for i in items}
    level = BADGE_LEVEL_INFO
    if INSIGHT_CRITICAL in levels:
        level = "critical"
    elif INSIGHT_WARNING in levels:
        level = "warning"
    elif "success" in levels:
        level = BADGE_LEVEL_SUCCESS
    return BadgeSnapshot(
        count=min(len(items), 99),
        dot=True,
        level=level,
        tooltip=f"{len(items)} copilot insight(s)",
    )


def help_badge_resolver(request, *, slot, page_path):  # noqa: ARG001
    """Hot KB article count for the current page path. Stub for Wave D."""
    return None


def feedback_badge_resolver(request, *, slot, page_path):  # noqa: ARG001
    """Pending feedback notifications — currently None (Wave D)."""
    return None


def context_badge_resolver(request, *, slot, page_path):  # noqa: ARG001
    """Drawer always-fresh; no badge unless an alert is pinned."""
    return None


def back_to_top_badge_resolver(request, *, slot, page_path):  # noqa: ARG001
    """Back-to-top has no badge semantic. Always None."""
    return None


def presence_badge_resolver(request, *, slot, page_path):  # noqa: ARG001
    """Co-viewer count on the current page (excluding the requester).

    Wave E1 — reads the in-process presence tracker. Cross-worker
    visibility deferred (would need Redis pub/sub).
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    user_id = getattr(user, "pk", 0) or 0
    try:
        from .presence import count_present
    except (ImportError, RuntimeError):
        return None
    count = count_present(page_path=page_path, exclude_user_id=user_id)
    if not count:
        return None
    return BadgeSnapshot(
        count=min(count, 99),
        dot=True,
        level=BADGE_LEVEL_SUCCESS,
        tooltip=f"{count} other operator(s) on this page",
    )


# Register on import — loaded by AppConfig.ready.
register_badge_resolver("messages", messages_badge_resolver)
register_badge_resolver("ai-copilot", ai_copilot_badge_resolver)
register_badge_resolver("help", help_badge_resolver)
register_badge_resolver("feedback", feedback_badge_resolver)
register_badge_resolver("context", context_badge_resolver)
register_badge_resolver("back-to-top", back_to_top_badge_resolver)
register_badge_resolver("presence", presence_badge_resolver)
