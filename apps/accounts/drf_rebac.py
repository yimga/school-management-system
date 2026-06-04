"""DRF permission classes backed by Postgres ReBAC + colon RBAC dual-run."""

from __future__ import annotations

from rest_framework.permissions import BasePermission


def school_from_request(request):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    session = getattr(request, "session", None)
    school_id = getattr(session, "get", lambda _k, _d=None: None)("school_id") if session else None
    if not school_id:
        return None
    from apps.schools.models import School

    session_school = School.objects.filter(pk=school_id, is_active=True).first()
    if session_school is None:
        return None
    try:
        from apps.schools.middleware import _resolve_school_from_request

        host_school = _resolve_school_from_request(request)
    except (ImportError, AttributeError, TypeError, ValueError):
        host_school = None
    if host_school is not None and str(host_school.pk) != str(session_school.pk):
        return None
    if session is not None:
        from apps.schools.session_school_bind import verify_session_school_bind

        user = getattr(request, "user", None)
        if user and not verify_session_school_bind(session, user):
            return None
    return session_school


class RebacPermission(BasePermission):
    """Require ``enforce_permission_token`` for the given colon capability code."""

    def __init__(self, code: str):
        self.code = (code or "").strip()

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        from apps.accounts.rebac import enforce_permission_token

        return enforce_permission_token(
            user,
            self.code,
            school=school_from_request(request),
        )


class RebacPermissionOrReadOnly(RebacPermission):
    """SAFE methods use read_code; mutations use write_code."""

    def __init__(self, *, read_code: str, write_code: str):
        self.read_code = read_code
        self.write_code = write_code

    def has_permission(self, request, view) -> bool:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            checker = RebacPermission(self.read_code)
        else:
            checker = RebacPermission(self.write_code)
        return checker.has_permission(request, view)
