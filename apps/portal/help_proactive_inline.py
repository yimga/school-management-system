"""
Inline proactive help nudges on high-friction routes (batch 1352).
"""

from __future__ import annotations

from typing import Any

from apps.portal.school_help_context import friction_route_prefixes, is_friction_route


def proactive_nudge_for_request(request) -> dict[str, Any] | None:
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None
    path = getattr(request, "path", "") or ""
    if not is_friction_route(path):
        return None
    try:
        from django.urls import reverse

        help_url = reverse("feedback:help_center")
        kb_url = reverse("kb:kb_home")
    except Exception:
        return None
    module = _module_from_path(path)
    return {
        "module": module,
        "help_url": help_url,
        "kb_url": kb_url,
        "message_key": f"help.nudge.{module}",
    }


def _module_from_path(path: str) -> str:
    p = (path or "").lower().strip("/")
    for prefix in friction_route_prefixes():
        seg = prefix.strip("/").split("/")[0]
        if seg and p.startswith(seg):
            return seg
    return "general"
