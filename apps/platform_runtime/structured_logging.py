"""
§2.4 Exception discipline: structured logging with tenant/actor/route context.
Use where broad except is retained (allowlisted) so failures are auditable.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def log_exception_with_context(
    message: str,
    *,
    tenant_id: Optional[str] = None,
    school_id: Optional[Any] = None,
    actor_id: Optional[Any] = None,
    route: Optional[str] = None,
    exc_info: bool = True,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log an exception with tenant/actor/route context for audit and debugging.
    Call from except blocks that must not swallow silently (allowlisted broad except).
    """
    log_extra = dict(extra or {})
    if tenant_id is not None:
        log_extra["tenant_id"] = str(tenant_id)
    if school_id is not None:
        log_extra["school_id"] = str(school_id)
    if actor_id is not None:
        log_extra["actor_id"] = str(actor_id)
    if route is not None:
        log_extra["route"] = route
    logger.warning(
        message,
        exc_info=exc_info,
        extra=log_extra,
    )


def request_context_for_log(request: Any) -> dict[str, Any]:
    """Extract tenant_id, school_id, actor_id, route from request for structured logging."""
    out: dict[str, Any] = {}
    school = getattr(request, "school", None)
    if school and getattr(school, "id", None) is not None:
        out["school_id"] = str(school.id)
        out["tenant_id"] = str(school.id)  # often same as school_id in single-tenant-per-schema
    user = getattr(request, "user", None)
    if user and getattr(user, "id", None) is not None:
        out["actor_id"] = str(user.id)
    if getattr(request, "path", None):
        out["route"] = request.path
    return out
