"""
Structured surface / product observability hooks.

Logs are JSON-friendly for log aggregation (school_id, surface, user_id).
Does not replace security audit logs or platform events for automation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("rmc.observability")


def record_tenant_surface_view(
    *,
    surface: str,
    request,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """
    Record a tenant-authenticated UI surface view (catalog, onboarding, etc.).
    Safe to call on every GET; keep volume reasonable by only using for key surfaces.
    """
    school = getattr(request, "school", None)
    school_id = getattr(school, "pk", None)
    user = getattr(request, "user", None)
    user_id = getattr(user, "pk", None) if user and user.is_authenticated else None
    payload = {
        "event": "tenant_surface_view",
        "surface": surface,
        "school_id": str(school_id) if school_id is not None else None,
        "user_id": str(user_id) if user_id is not None else None,
        "path": getattr(request, "path", "") or "",
    }
    if extra:
        payload["extra"] = extra
    logger.info("rmc.observability %s", payload)
