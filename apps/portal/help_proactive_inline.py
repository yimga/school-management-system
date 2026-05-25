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


_INLINE_ASSISTANT_PREFIXES = (
    "/finance/",
    "/payroll/",
    "/evals/",
    "/attendance/",
    "/teacher/attendance",
    "/studio_os/",
    "/studio-os/",
    "/super/migration/",
    "/portal/configure/migration/",
    "/migration/",
    "/siteconfig/",
)


# Paths that get inline assistant without requiring "dashboard" in URL (batch 1394).
_INLINE_ASSISTANT_EXACT = (
    "/teacher/attendance",
    "/teacher/attendance/",
)


def module_inline_assistant_for_request(request) -> dict[str, Any]:
    """Full inline KB copilot on finance/payroll/evals/attendance/studio routes (batch 1356 + 1394)."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    path = (getattr(request, "path", "") or "").lower()
    slug = ""
    for prefix in _INLINE_ASSISTANT_PREFIXES:
        if path.startswith(prefix):
            slug = prefix.strip("/").split("/")[0]
            if slug == "studio_os" or slug == "studio-os":
                slug = "studio"
            elif slug == "super" and path.startswith("/super/migration"):
                slug = "migration"
            elif slug == "portal" and "migration" in path:
                slug = "migration"
            elif slug == "siteconfig":
                slug = "siteconfig"
            break
    if not slug:
        return {}
    path_ok = (
        "dashboard" in path
        or "compliance" in path
        or "command_center" in path
        or "console" in path
        or path.endswith("/new/")
        or path.endswith("/new")
        or any(path.startswith(p) or path.startswith(p + "/") for p in _INLINE_ASSISTANT_EXACT)
        or path.startswith("/studio_os")
        or path.startswith("/studio-os")
        or path.startswith("/super/migration")
        or path.startswith("/portal/configure/migration")
        or path.startswith("/migration/")
        or path.startswith("/siteconfig/")
    )
    if not path_ok:
        return {}
    return {
        "show_module_inline_help_assistant": True,
        "help_module_slug": slug,
    }


def _module_from_path(path: str) -> str:
    p = (path or "").lower().strip("/")
    for prefix in friction_route_prefixes():
        seg = prefix.strip("/").split("/")[0]
        if seg and p.startswith(seg):
            return seg
    return "general"
