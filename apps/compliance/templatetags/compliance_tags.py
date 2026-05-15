"""
Pass 9: template tags for compliance UI bits.

Provides a drop-in `recent_activity_for` inclusion tag so any detail page can
render an audit-log drill-down without view-level wiring.
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.inclusion_tag(
    "compliance/partials/recent_activity_panel.html", takes_context=True
)
def recent_activity_for(context, model_name: str, object_id, days: int = 90, limit: int = 50):
    """
    Render the recent-activity panel for `(model_name, object_id)`.

    Safe to call from any template; returns an empty `recent_activity_logs`
    list when AuditLog is unavailable or when the lookup fails. Tenant-scopes
    the queryset to ``request.school`` when present so cross-tenant audit
    leakage is impossible.
    """
    request = context.get("request")
    if request is None:
        return {"recent_activity_logs": []}
    from apps.compliance.audit_panel import recent_activity_logs_for  # noqa: PLC0415
    return {
        "recent_activity_logs": recent_activity_logs_for(
            request, model_name=model_name, object_id=object_id, days=days, limit=limit
        ),
    }
