"""School-scoped AccessRole helpers — global templates vs tenant catalog."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.models import AccessRole


def roles_queryset_for_school(school) -> QuerySet:
    """
    Roles assignable at a school: platform-global templates (school=NULL) plus
    this school's catalog rows.
    """
    if school is None:
        return AccessRole.objects.filter(school__isnull=True).order_by("code")
    return (
        AccessRole.objects.filter(Q(school__isnull=True) | Q(school_id=school.pk))
        .order_by("school_id", "code")
    )


def role_applies_to_school(role, school) -> bool:
    if role is None:
        return False
    if getattr(role, "school_id", None) is None:
        return True
    if school is None:
        return False
    return role.school_id == school.pk


def roles_filter_q(school) -> Q:
    """Q object for M2M / FK filters on AccessRole in permission checks."""
    if school is None:
        return Q()
    return Q(school__isnull=True) | Q(school_id=school.pk)
