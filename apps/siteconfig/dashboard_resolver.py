"""
Phase 4 — Dashboard hub (24.4). Single entry point for role-based dashboard composition.

Apps should call dashboard_resolver.for_role(school, role, user=None) instead of
calling resolve_dashboard_widgets / get_tenant_dashboard_registry directly, so
all dashboard logic stays in one place and can be extended (e.g. TenantDashboardAssignment).
"""
from __future__ import annotations

from typing import Any

from .models_support import resolve_dashboard_widgets
from .dashboard_registry import get_tenant_dashboard_registry


def for_role(
    school,
    role: str | None,
    user=None,
    preference=None,
    page: str | None = None,
    *,
    include_registry: bool = False,
) -> dict[str, Any]:
    """
    Return composed dashboard for the given school/role (and optional user preference).

    If include_registry is True, also returns the full widget registry for the role/page
    (for admin or layout API). Otherwise returns only widget keys and metadata needed for rendering.
    """
    role = (role or "").strip().upper() or None
    if preference is None and user is not None:
        preference = getattr(user, "preferences", None) or getattr(user, "user_preference", None)

    widget_keys = resolve_dashboard_widgets(role, preference)

    result = {
        "role": role,
        "widget_keys": widget_keys,
        "page": page,
    }

    if include_registry or page:
        result["registry"] = get_tenant_dashboard_registry(school, role=role, page=page or "backend")

    # Phase 3 lineage: register dashboard resolution for this role (consumer_type=dashboard, consumer_code=role).
    try:
        from apps.metadata.usage_registry import register_usage
        register_usage("dashboard", (role or "unknown").lower(), "dashboard", "widget_keys")
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    return result
