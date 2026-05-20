"""Forum compose AI copilot context (batch 1360)."""

from __future__ import annotations

from typing import Any


def forum_compose_assistant_for_request(request) -> dict[str, Any]:
    """KB-grounded AI panel on new-topic and reply compose surfaces."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    path = (getattr(request, "path", "") or "").lower()
    if "/forums/new" in path:
        return {
            "show_forum_compose_assistant": True,
            "forum_compose_mode": "new_topic",
        }
    if "/forums/topic/" in path and request.method == "GET":
        return {
            "show_forum_compose_assistant": True,
            "forum_compose_mode": "reply",
        }
    return {}
