"""
Pass 9: view-level audit decorators.

PII-VIEW logging closes the FERPA read-access gap by emitting an AuditLog row
each time an authenticated user GETs a high-sensitivity detail view (student,
evaluation, invoice, …). The hot path is a single insert per request, fail-safe:
audit errors never propagate to the user.
"""

from __future__ import annotations

import functools
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _resolve_object_id(request, kwargs: dict, object_id_kwarg: str) -> str:
    value = kwargs.get(object_id_kwarg)
    if value is None:
        value = request.GET.get(object_id_kwarg) or request.POST.get(object_id_kwarg)
    return str(value) if value not in (None, "") else ""


def _emit_view_event(
    *,
    request,
    model_name: str,
    object_id: str,
    sensitivity: str,
    reason: str = "",
) -> None:
    """Best-effort AuditLog write. Swallows any exception."""
    try:
        from apps.compliance.models_audit import AuditLog
    except (ImportError, ModuleNotFoundError):
        return
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return
    try:
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.VIEW,
            model_name=model_name,
            object_id=object_id,
            object_repr=f"{model_name}#{object_id}" if object_id else model_name,
            sensitivity=sensitivity or AuditLog.Sensitivity.HIGH,
            ip_address=_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
            app_label=getattr(request.resolver_match, "app_name", "") or "",
            reason=reason[:255] if reason else "",
        )
    except Exception:  # noqa: BLE001 - audit log must never break the request
        logger.debug("audit_pii_view: failed to record VIEW event", exc_info=True)


def _client_ip(request) -> Optional[str]:
    """Client IP from the outermost TRUSTED proxy hop, or ``None``.

    ``X-Forwarded-For`` is client-controlled to the LEFT, so the leftmost hop
    is whatever the caller typed -- an audit row stamped with it records the
    attacker's choice of source address, not the request's.
    """
    from apps.api.rate_limit import client_ip as _trusted_client_ip

    ip = _trusted_client_ip(request)
    return ip if ip and ip != "unknown" else None


def audit_pii_view(
    *,
    model_name: str,
    object_id_kwarg: str = "pk",
    sensitivity: Optional[str] = None,
    reason: str = "",
) -> Callable:
    """
    Decorator: record an AuditLog VIEW row each time the wrapped view returns a
    2xx response on a GET request.

    Usage::

        @audit_pii_view(model_name="StudentProfile", object_id_kwarg="pk", sensitivity="HIGH")
        def student_detail(request, pk): ...

    For class-based views, apply via ``method_decorator`` on dispatch or get.
    """

    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(*args, **kwargs):
            # args[0] is `request` for function views; (self, request, …) for CBV methods.
            request = args[0] if args and hasattr(args[0], "method") else (
                args[1] if len(args) > 1 else None
            )
            response = view_func(*args, **kwargs)
            try:
                if (
                    request is not None
                    and request.method == "GET"
                    and 200 <= getattr(response, "status_code", 500) < 300
                ):
                    object_id = _resolve_object_id(request, kwargs, object_id_kwarg)
                    _emit_view_event(
                        request=request,
                        model_name=model_name,
                        object_id=object_id,
                        sensitivity=sensitivity or "",
                        reason=reason,
                    )
            except Exception:  # noqa: BLE001
                logger.debug("audit_pii_view wrapper failed", exc_info=True)
            return response

        return wrapper

    return decorator
