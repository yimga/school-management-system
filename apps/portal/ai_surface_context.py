"""
Unified AI surface context (batch 1393 — one brain, many surfaces).

Every help/copilot/command-bar entry point should build context from here so
role, school, and current_path stay consistent across AI Center, floating
copilot, KB assistant, and engine-room gateway calls.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "build_ai_surface_context",
    "active_url_from_context",
    "merge_surface_metadata",
]


def build_ai_surface_context(request) -> dict[str, Any]:
    """Role + tenant + path pack for AI invocations."""
    user = getattr(request, "user", None)
    school = getattr(request, "school", None)
    path = (getattr(request, "path", None) or "")[:500]
    role = ""
    user_id = None
    if user is not None and getattr(user, "is_authenticated", False):
        role = (getattr(user, "role", None) or "") or ""
        user_id = getattr(user, "pk", None)
    from apps.portal.ai_intent_router import intent_metadata, resolve_surface_intent

    intent = resolve_surface_intent(path, role)
    return {
        "current_path": path,
        "active_url": path,
        "role": role,
        "school_id": getattr(school, "pk", None),
        "school": school,
        "user_id": user_id,
        "request": request,
        "surface_intent": intent,
        "surface_intent_meta": intent_metadata(intent),
    }


def active_url_from_context(
    ctx: dict[str, Any] | None,
    *,
    fallback: str = "",
) -> str:
    if not ctx:
        return (fallback or "")[:500]
    return (
        (ctx.get("active_url") or ctx.get("current_path") or fallback) or ""
    )[:500]


def merge_surface_metadata(
    base: dict[str, Any] | None,
    ctx: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge gateway metadata with surface context (request stripped)."""
    out = dict(base or {})
    if not ctx:
        return out
    for key in (
        "current_path",
        "active_url",
        "role",
        "school_id",
        "user_id",
        "surface_intent",
        "surface_intent_meta",
    ):
        val = ctx.get(key)
        if val is not None and val != "":
            out[key] = val
    if ctx.get("school") is not None and "school" not in out:
        out["school"] = ctx["school"]
    if ctx.get("request") is not None and "request" not in out:
        out["request"] = ctx["request"]
    return out
