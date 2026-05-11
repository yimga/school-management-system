"""
Pass 9: template tags for compliance UI bits.

Provides a drop-in `recent_activity_for` inclusion tag so any detail page can
render an audit-log drill-down without view-level wiring.
"""

from __future__ import annotations

from datetime import timedelta

from django import template
from django.utils import timezone

register = template.Library()


@register.inclusion_tag("compliance/partials/recent_activity_panel.html")
def recent_activity_for(model_name: str, object_id, days: int = 90, limit: int = 50):
    """
    Render the recent-activity panel for `(model_name, object_id)`.

    Safe to call from any template; returns an empty `recent_activity_logs`
    list when AuditLog is unavailable or when the lookup fails.
    """
    logs = []
    if object_id in (None, ""):
        return {"recent_activity_logs": []}
    try:
        from apps.compliance.models_audit import AuditLog

        start = timezone.now() - timedelta(days=int(days))
        logs = list(
            AuditLog.objects.filter(
                model_name=model_name,
                object_id=str(object_id),
                timestamp__gte=start,
            )
            .select_related("user")
            .order_by("-timestamp")[:limit]
        )
    except Exception:  # noqa: BLE001 - drill-down must never break the page
        logs = []
    return {"recent_activity_logs": logs}
