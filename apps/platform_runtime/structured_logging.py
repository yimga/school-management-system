"""
§2.4 Exception discipline: structured logging with tenant/actor/route context.

Use where broad except is retained (allowlisted) so failures are auditable.
All helpers attach structured context (tenant_id, school_id, actor_id, route) so
logs can be queried by tenant/actor/route. See docs/broad_exception_audit.md and
RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §2.4.

Example (view):
    try:
        do_thing()
    except (ValueError, TypeError) as e:
        log_view_exception(request, "do_thing failed", extra={"step": "validate"})
        return HttpResponseBadRequest(...)

Example (task/celery, no request):
    log_exception_with_context(
        "provision_school_sync failed",
        school_id=school_id,
        extra={"task_id": task_id},
    )
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

    Call from except blocks that must not swallow silently (allowlisted broad
    except). Context fields are added to the log record's extra dict so they
    are queryable in log aggregation.

    Args:
        message: Human-readable description of the failure.
        tenant_id: Optional tenant/schema identifier.
        school_id: Optional school identifier (often same as tenant_id).
        actor_id: Optional user/actor identifier.
        route: Optional request path or route name.
        exc_info: If True, include exception traceback (default True).
        extra: Optional additional key-value context; merged with context fields.
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
    """Extract tenant_id, school_id, actor_id, route, runtime_trace_id from request for structured logging."""
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
    trace_id = getattr(request, "_runtime_trace_id", None)
    if trace_id:
        out["runtime_trace_id"] = trace_id  # GAP.5: resolver path tracing
    return out


def log_view_exception(
    request: Any,
    message: str,
    *,
    exc_info: bool = True,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """
    One-line structured logging from view code.

    Uses request to populate tenant_id, school_id, actor_id, and route. Prefer
    this in view except blocks so failures are auditable (§10 structured
    logging everywhere). request is typically HttpRequest; None is handled
    (context will be empty).
    """
    ctx = request_context_for_log(request) if request else {}
    log_exception_with_context(
        message,
        tenant_id=ctx.get("tenant_id"),
        school_id=ctx.get("school_id"),
        actor_id=ctx.get("actor_id"),
        route=ctx.get("route"),
        exc_info=exc_info,
        extra=extra,
    )
