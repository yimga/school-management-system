"""Per-record audit drill-down helper — Pass 9 platform-wide adoption.

`recent_activity_logs_for(model_name, object_id)` returns the last N days
of AuditLog rows for a single object, scoped to the requesting user's
tenant via the existing `scope_audit_logs` helper. Detail views call it
to populate the `recent_activity_logs` context var consumed by
`templates/compliance/partials/recent_activity_panel.html`.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from django.db import DatabaseError
from django.utils import timezone

from apps.compliance.models_audit import AuditLog
from apps.compliance.tenant_scope import scope_audit_logs

_DEFAULT_DAYS = 90
_PANEL_LIMIT = 25


def recent_activity_logs_for(
    request,
    *,
    model_name: str,
    object_id: int | str,
    days: int = _DEFAULT_DAYS,
    limit: int = _PANEL_LIMIT,
) -> Iterable[AuditLog]:
    """Return the recent AuditLog rows for one record, tenant-scoped.

    Returns an empty list on any DB / scoping failure so a missing
    audit table never breaks a detail page.
    """
    if not model_name or object_id in (None, ""):
        return []
    try:
        cutoff = timezone.now() - timedelta(days=days)
        qs = AuditLog.objects.filter(
            model_name=model_name,
            object_id=str(object_id),
            timestamp__gte=cutoff,
        ).order_by("-timestamp").select_related("user")
        school = getattr(request, "school", None)
        scoped = scope_audit_logs(qs, school) if school is not None else qs
        return list(scoped[:limit])
    except (DatabaseError, AttributeError, ValueError):
        return []
