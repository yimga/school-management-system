from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from apps.accounts.models import User
from apps.schools.control_plane import user_has_control_plane_access


def get_compliance_scope_school(request):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    if user_has_control_plane_access(getattr(request, "user", None)):
        return None
    raise PermissionDenied("School context required.")


def school_user_queryset(school):
    queryset = User.objects.all()
    if school is None:
        return queryset
    return queryset.filter(
        Q(school_memberships__school=school)
        | Q(teacher_profile__school=school)
        | Q(student_profile__school=school)
    ).distinct()


def scope_audit_logs(queryset, school):
    if school is None:
        return queryset
    return queryset.filter(user_id__in=school_user_queryset(school).values("id"))


def scope_access_logs(queryset, school):
    if school is None:
        return queryset
    return queryset.filter(user_id__in=school_user_queryset(school).values("id"))


def scope_sessions(queryset, school):
    if school is None:
        return queryset
    return queryset.filter(user_id__in=school_user_queryset(school).values("id"))
