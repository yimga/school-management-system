"""
School-scoped help context for engine-room prompts (batch 1346).
"""

from __future__ import annotations

from typing import Any


def build_school_help_context_block(*, school: Any | None, user: Any | None) -> str:
    """Plain-text block injected into support_suggest (no PII beyond school name)."""
    if school is None:
        return ""
    lines: list[str] = ["School context:"]
    name = getattr(school, "name", None) or getattr(school, "slug", None)
    if name:
        lines.append(f"- School: {str(name)[:80]}")
    country = getattr(school, "country_code", None) or getattr(school, "country", None)
    if country:
        lines.append(f"- Region: {str(country)[:8]}")
    plan = getattr(school, "plan_tier", None) or getattr(school, "subscription_tier", None)
    if plan:
        lines.append(f"- Plan: {str(plan)[:40]}")
    if user is not None:
        role = getattr(user, "role", None)
        if role:
            lines.append(f"- User role: {str(role)[:32]}")
    return "\n".join(lines)


def contextual_help_drawer_enabled(request) -> bool:
    try:
        from apps.portal.help_governance import ai_help_enabled_for_request

        if not ai_help_enabled_for_request(request):
            return False
    except Exception:
        pass
    return bool(getattr(request, "user", None) and request.user.is_authenticated)


def friction_route_prefixes() -> tuple[str, ...]:
    return (
        "/finance/",
        "/payroll/",
        "/evals/",
        "/compliance/",
        "/analytics/",
        "/feedback/",
        "/authentication/backend/",
        "/portal/teacher",
        "/portal/parent",
    )


def is_friction_route(path: str) -> bool:
    p = (path or "").lower()
    return any(p.startswith(prefix) for prefix in friction_route_prefixes())
