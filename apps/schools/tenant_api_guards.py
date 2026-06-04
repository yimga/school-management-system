"""
Tenant API guards — resolve ``school_id`` / ``tenant`` query params with membership checks.

Use on internal JSON APIs that accept a client-supplied campus identifier so a
user on school A cannot read school B data (BOLA/IDOR).
"""

from __future__ import annotations

from typing import Any

from django.http import JsonResponse


def session_school_id_from_request(request) -> str | None:
    if not hasattr(request, "session"):
        return None
    sid = (request.session.get("school_id") or "").strip()
    return sid or None


def staff_may_bypass_tenant_guard_on_request(request) -> bool:
    """Control-plane operators on manager/local hosts may cross tenant query params."""
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    from apps.schools.control_plane import user_has_control_plane_access

    if not user_has_control_plane_access(user):
        return False
    host_kind = (getattr(request, "public_host_kind", None) or "").lower()
    return host_kind in {"manager", "local"}


def user_may_operate_on_school(request, school: Any) -> bool:
    if school is None:
        return False
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if staff_may_bypass_tenant_guard_on_request(request):
        return True

    host_kind = (getattr(request, "public_host_kind", None) or "").lower()
    if host_kind not in {"manager", "local"}:
        from apps.schools.models import SchoolMembership

        return SchoolMembership.objects.filter(user=user, school=school).exists()

    from apps.schools.tenant_switch_security import user_may_access_school_api

    return user_may_access_school_api(
        user, school, session_school_id=session_school_id_from_request(request)
    )


def resolve_school_from_request_param(
    request,
    *,
    param: str = "school_id",
    allow_host_school: bool = True,
) -> tuple[Any | None, JsonResponse | None]:
    """
    Resolve ``School`` from ``request.school`` or ``?school_id=``.

    Returns ``(school, None)`` or ``(None, error_response)``.
    Staff/superuser may access any active school; others require membership.
    """
    from apps.schools.models import School

    host_school = getattr(request, "school", None) if allow_host_school else None
    sid_raw = (request.GET.get(param) or "").strip()

    if host_school is not None and not sid_raw:
        school = host_school
    elif sid_raw:
        school = School.objects.filter(pk=sid_raw, is_active=True).first()
        if school is None:
            try:
                sid_int = int(sid_raw)
            except (TypeError, ValueError):
                sid_int = None
            if sid_int is not None:
                school = School.objects.filter(pk=sid_int, is_active=True).first()
    elif host_school is not None:
        school = host_school
    else:
        return None, JsonResponse(
            {
                "error": "school context required",
                "hint": f"Open in tenant context or pass {param}.",
            },
            status=400,
        )

    if school is None:
        return None, JsonResponse({"error": "school not found"}, status=404)

    if not user_may_operate_on_school(request, school):
        return None, JsonResponse({"error": "Forbidden"}, status=403)

    return school, None


__all__ = [
    "resolve_school_from_request_param",
    "session_school_id_from_request",
    "staff_may_bypass_tenant_guard_on_request",
    "user_may_operate_on_school",
]
