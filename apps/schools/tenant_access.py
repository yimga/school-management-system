"""
Tenant-scoped querysets and coarse action permissions (SLICE 10 — security hardening).

Use after request.school is resolved; fail closed when school is missing.

Authentication policy (MFA, step-up, device trust) is enforced before these checks in the
accounts/sign-in stack. ``has_school_permission`` is **post-auth** tenant RBAC: membership,
feature permissions, and school role — not a substitute for MFA configuration.
"""

from __future__ import annotations

from typing import Any, Literal

from django.db.models import QuerySet

from apps.accounts.models import User

SchoolAction = Literal["view", "edit", "export", "admin"]

_LEARNER_MEMBERSHIP_ROLES = frozenset({"PARENT", "STUDENT", "EMPLOYER"})


def safe_queryset_for_school(
    queryset: QuerySet[Any],
    school,
    *,
    school_field: str = "school_id",
) -> QuerySet[Any]:
    """
    Filter a queryset to a single tenant. Returns .none() if school is missing.
    ``school_field`` is the ORM lookup (e.g. ``school_id`` or ``school`` for FK).
    """
    if school is None:
        return queryset.none()
    if school_field == "school":
        return queryset.filter(school=school)
    return queryset.filter(**{school_field: school.pk})


def user_belongs_to_school(user: User, school) -> bool:
    if not user.is_authenticated or school is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    from apps.schools.models import SchoolMembership

    return SchoolMembership.objects.filter(
        user_id=user.pk, school_id=school.pk
    ).exists()


def has_school_permission(user: User, school, action: SchoolAction) -> bool:
    """
    Coarse school-scoped permission. Superusers pass for all actions.

    - view: school membership (or superuser)
    - edit: membership + not a parent/student-only role on membership
    - export: membership + (settings.manage or reports.manage or attendance.manage),
      or staff roles aligned with portal attendance CSV (ADMIN/LEADERSHIP/…/TEACHER)
    - admin: membership + settings.manage
    """
    if not user.is_authenticated or school is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not user_belongs_to_school(user, school):
        return False

    from apps.schools.models import SchoolMembership

    m = SchoolMembership.objects.filter(user_id=user.pk, school_id=school.pk).first()
    if m is None:
        return False
    mrole = str(m.role or "").strip().upper()

    if action == "view":
        return True

    if action == "edit":
        if mrole in _LEARNER_MEMBERSHIP_ROLES:
            return user.has_feature_permission("grades.enter") or user.has_feature_permission(
                "settings.manage"
            )
        return True

    if action in ("export", "admin"):
        if action == "export":
            if user.has_feature_permission("settings.manage") or user.has_feature_permission(
                "reports.manage"
            ):
                return True
            if user.has_feature_permission("attendance.manage"):
                return True
            # Portal student attendance CSV: roles aligned with ``attendance_exports.user_can_access`` (membership required).
            _export_roles = frozenset(
                {
                    "ADMIN",
                    "LEADERSHIP",
                    "IT_ADMIN",
                    "PRINCIPAL",
                    "VICE_PRINCIPAL",
                    "TEACHER",
                }
            )
            if mrole in _export_roles:
                return True
            return False
        return user.has_feature_permission("settings.manage")

    return False


# Re-export (implementation: ``hierarchy_helpers``).
from apps.schools.hierarchy_helpers import scoped_schools_for_user  # noqa: E402,F401
