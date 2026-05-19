"""
Campus / school switch authorization — BOLA/IDOR guard for MeSwitchSchoolView.

Membership on the target school always wins. District operators who are members of a
parent campus may switch into an active child campus in that hierarchy without a
separate child membership row.
"""

from __future__ import annotations

from typing import Any


def user_may_switch_to_school(
    user: Any,
    target_school: Any,
    *,
    active_school: Any | None = None,
) -> bool:
    """Return True when the user may bind session school_id to target_school."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if target_school is None or not getattr(target_school, "is_active", True):
        return False
    if getattr(user, "is_superuser", False):
        return True

    from apps.schools.models import SchoolMembership

    if SchoolMembership.objects.filter(user=user, school=target_school).exists():
        return True

    if active_school is None:
        return False

    if not SchoolMembership.objects.filter(user=user, school=active_school).exists():
        return False

    # Nested tenancy: parent-campus member may enter a direct child workspace.
    if getattr(target_school, "parent_school_id", None) == getattr(
        active_school, "pk", None
    ):
        return True

    # Allow switching up to parent when currently on a child (return to district root).
    if getattr(active_school, "parent_school_id", None) == getattr(
        target_school, "pk", None
    ):
        return True

    return False


def schools_user_may_operate_on(
    user: Any,
    *,
    active_school: Any | None = None,
) -> list[Any]:
    """
    Return active schools the user may bind or access (membership + hierarchy).

    Used by API list endpoints to avoid leaking foreign tenant ids in switch UIs.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    from apps.schools.models import School, SchoolMembership

    if getattr(user, "is_superuser", False):
        return list(School.objects.filter(is_active=True).order_by("name")[:200])

    member_ids = list(
        SchoolMembership.objects.filter(user=user).values_list("school_id", flat=True)  # tenant-isolation-allow: user-scoped-school-membership-switch-list
    )
    if not member_ids:
        return []

    schools = list(
        School.objects.filter(pk__in=member_ids, is_active=True).order_by("name")
    )
    allowed_ids = {s.pk for s in schools}
    for parent in schools:
        for child in School.objects.filter(
            parent_school_id=parent.pk, is_active=True
        ).only("pk", "name", "slug", "subdomain", "is_active", "parent_school_id"):
            if child.pk not in allowed_ids and user_may_switch_to_school(
                user, child, active_school=active_school or parent
            ):
                schools.append(child)
                allowed_ids.add(child.pk)
    return schools


def user_may_access_school_api(
    user: Any,
    school: Any,
    *,
    session_school_id: str | None = None,
) -> bool:
    """
    Return True when user may read/write tenant-scoped API data for school.

    Covers direct membership, parent→child hierarchy (district operator on child host),
    and session active school used for switch rules.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if school is None or not getattr(school, "is_active", True):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    from apps.schools.models import School, SchoolMembership

    if SchoolMembership.objects.filter(user=user, school=school).exists():
        return True

    if session_school_id:
        active = School.objects.filter(pk=session_school_id, is_active=True).first()
        if active and user_may_switch_to_school(user, school, active_school=active):
            return True

    for mid in SchoolMembership.objects.filter(user=user).values_list(  # tenant-isolation-allow: user-scoped-school-membership-switch-graph
        "school_id", flat=True
    ):
        active = School.objects.filter(pk=mid, is_active=True).first()
        if active and user_may_switch_to_school(user, school, active_school=active):
            return True
    return False
