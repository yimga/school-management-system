"""Tenant-scoped identity helpers — membership, effective role, staff queryset."""

from __future__ import annotations


from django.contrib.auth import get_user_model
from django.db.models import QuerySet


def users_queryset_for_school(school) -> QuerySet:
    """Users with membership on this school (active users only)."""
    User = get_user_model()
    if school is None:
        return User.objects.none()
    return (
        User.objects.filter(
            school_memberships__school_id=school.pk,
            is_active=True,
        )
        .distinct()
        .order_by("username")
    )


def user_has_school_membership(user, school) -> bool:
    if not user or not getattr(user, "is_authenticated", False) or school is None:
        return False
    from apps.schools.models import SchoolMembership

    return SchoolMembership.objects.filter(user_id=user.pk, school_id=school.pk).exists()


def localized_role_for_user(user, school) -> str:
    """Effective role code with tenant-local display label when configured."""
    from apps.accounts.iam_localization import localized_role_label

    code = get_effective_role(user, school)
    fallback = ""
    if user is not None:
        try:
            fallback = user.get_role_display()
        except Exception:
            fallback = code
    return localized_role_label(code, school, fallback=fallback or code)


def get_effective_role(user, school=None) -> str:
    """
    Resolve role for MFA/module checks: membership role on school wins, else User.role.
    """
    if not user:
        return ""
    if school is not None:
        from apps.schools.models import SchoolMembership

        m = (
            SchoolMembership.objects.filter(user_id=user.pk, school_id=school.pk)
            .values_list("role", flat=True)
            .first()
        )
        if m:
            return str(m).strip().upper()
    return (getattr(user, "role", "") or "").strip().upper()


def assert_user_in_school_or_raise(user, school) -> None:
    from django.core.exceptions import PermissionDenied

    if not user_has_school_membership(user, school):
        raise PermissionDenied("User is not a member of this school.")


def mfa_enrolled_for_user(user) -> bool:
    from apps.accounts.mfa_setup_flow import mfa_has_device

    return mfa_has_device(user)


def school_mfa_compliance_rows(school) -> list[dict]:
    """Per-user MFA posture for tenant identity hub."""
    rows = []
    for user in users_queryset_for_school(school).select_related()[:500]:
        membership = user.school_memberships.filter(school_id=school.pk).first()
        rows.append(
            {
                "user": user,
                "membership_role": getattr(membership, "role", "") or "",
                "effective_role": get_effective_role(user, school),
                "mfa_ok": mfa_enrolled_for_user(user),
                "is_primary": getattr(membership, "is_primary", False),
            }
        )
    return rows
