"""School-scoped AccessRole helpers — global templates vs tenant catalog."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.models import AccessRole
from apps.accounts.superadmin import SUPERADMIN_ROLE_CODE


def _without_platform_top_role(qs: QuerySet) -> QuerySet:
    """Drop the platform SUPERADMIN template from an ASSIGNABLE-roles catalog.

    Migration 0058 creates a ``school IS NULL`` AccessRole coded ``SUPERADMIN``
    holding ``Permission.objects.all()``, and every global template is assignable
    at every school -- so this catalog offered a school owner a "Super
    Administrator" checkbox on ``/authentication/owner/people/``. Ticking it makes
    ``superadmin_reason()`` return ``assigned-role``, which makes
    ``has_feature_permission(<any code>, school=<any school>)`` return True at
    EVERY tenant the account touches. ``role_applies_to_school`` cannot refuse it:
    a global row applies everywhere by design.

    Promotion to platform super-admin has one sanctioned path
    (``superadmin_service`` / ``manage.py promote_superadmin``). A tenant form
    must not be a second one. Only the GLOBAL template is withheld -- a school's
    own catalog row coded SUPERADMIN grants exactly the permissions attached to
    it (see ``apps.accounts.superadmin``) and stays assignable.
    """
    return qs.exclude(code=SUPERADMIN_ROLE_CODE, school__isnull=True)


def roles_queryset_for_school(school) -> QuerySet:
    """
    Roles assignable at a school: platform-global templates (school=NULL) plus
    this school's catalog rows, minus the platform top role.
    """
    if school is None:
        return _without_platform_top_role(
            AccessRole.objects.filter(school__isnull=True)
        ).order_by("code")
    return _without_platform_top_role(
        AccessRole.objects.filter(Q(school__isnull=True) | Q(school_id=school.pk))
    ).order_by("school_id", "code")


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
