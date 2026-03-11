"""
Formal dashboard registry: tenant-scoped widget registration, metadata, permissions.
Aggregates built-in DashboardWidget catalog + marketplace installed widgets for a school/role/page.
"""

from typing import Any

from django.db import DatabaseError

from .models_dashboard import DashboardWidget, get_dashboard_widget_metadata


OPTIONAL_DASHBOARD_ERRORS = (AttributeError, DatabaseError, ImportError, TypeError, ValueError)


def get_tenant_dashboard_registry(
    school,
    role: str | None = None,
    page: str | None = None,
) -> dict[str, Any]:
    """
    Return the formal dashboard registry for a tenant: all available widgets with metadata and permissions.
    Used by dashboard UI and admin to list tenant-registered widgets (built-in + marketplace).
    """
    qs = DashboardWidget.objects.filter(is_active=True)
    if page:
        qs = qs.filter(page=page)
    if role and role.upper() != "ANY":
        from django.db.models import Q
        qs = qs.filter(Q(required_role="ANY") | Q(required_role=role.upper()))
    widgets = []
    widget_ids = []
    for w in qs.order_by("id"):
        widget_ids.append(w.id)
        allowed = getattr(w, "allowed_roles", None)
        widgets.append({
            "id": w.id,
            "name": w.name,
            "description": w.description or "",
            "widget_type": w.widget_type,
            "page": w.page,
            "required_role": w.required_role or "ANY",
            "allowed_roles": list(allowed) if isinstance(allowed, (list, tuple)) else [],
            "source": "builtin",
        })
    # Marketplace-installed widgets for this school
    installed = []
    if school:
        try:
            from apps.marketplace.services import get_installed_widgets
            for item in get_installed_widgets(school) or []:
                if not isinstance(item, dict):
                    continue
                widget_id = item.get("widget_id") or item.get("id")
                app_slug = item.get("app_slug", "")
                if not widget_id:
                    continue
                if page and item.get("page") and item.get("page") != page:
                    continue
                installed.append({
                    "id": widget_id,
                    "app_slug": app_slug,
                    "name": item.get("name", widget_id),
                    "config": item.get("config") or {},
                    "source": "marketplace",
                })
        except OPTIONAL_DASHBOARD_ERRORS:
            pass
    metadata = get_dashboard_widget_metadata(widget_ids) if widget_ids else {}
    # Register usage for metadata catalog (plan todo 4: hooks in dashboard definitions)
    consumer = f"dashboard:{page or 'backend'}"
    if role:
        consumer = f"{consumer}:{role}"
    try:
        from apps.metadata.usage_registry import register_usage
        register_usage("dashboard", consumer, "student", "admission_number")
        register_usage("dashboard", consumer, "person", "first_name")
        register_usage("dashboard", consumer, "invoice", "amount")
    except OPTIONAL_DASHBOARD_ERRORS:
        pass
    return {
        "widgets": widgets,
        "installed_app_widgets": installed,
        "metadata": metadata,
        "role": role,
        "page": page,
    }
