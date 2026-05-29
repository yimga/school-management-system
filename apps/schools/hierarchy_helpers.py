"""
Multi-campus / district hierarchy helpers (tenant-safe, fail-closed).

Uses ``School.parent_school``, ``hierarchy_path``, and iterative walks to avoid cycles.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Q, QuerySet

if TYPE_CHECKING:
    from apps.accounts.models import User

_SUBTREE_MEMBERSHIP_ROLES = frozenset(
    {
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "SUPERADMIN",
        "IT_ADMIN",
        "PROPRIETOR",
    }
)


def _school_model():
    from apps.schools.models import School

    return School


def hierarchy_link_would_cycle(school, proposed_parent_id) -> bool:
    """Return True if assigning proposed_parent_id to school would create a cycle."""
    if school is None or not proposed_parent_id:
        return False
    if proposed_parent_id == school.pk:
        return True
    School = _school_model()
    cursor = proposed_parent_id
    seen: set = {school.pk}
    depth = 0
    max_depth = 256
    while cursor and depth < max_depth:
        depth += 1
        if cursor in seen:
            return True
        seen.add(cursor)
        row = School.objects.filter(pk=cursor).values_list("parent_school_id", flat=True).first()
        if row == school.pk:
            return True
        cursor = row
    return depth >= max_depth


def get_school_ancestors(school) -> list:
    """Ancestors from root → immediate parent (breadcrumb-friendly)."""
    if school is None:
        return []
    chain = school.get_ancestor_chain()
    return list(reversed(chain))


def get_school_descendants(school, include_self: bool = False) -> QuerySet:
    """
    All descendant tenants under ``school`` (active only), breadth-first order by name.

    Uses iterative parent walks so behaviour stays correct even if hierarchy_path is stale.
    """
    School = _school_model()
    if school is None:
        return School.objects.none()

    collected: list = []
    q: deque = deque([school.pk])
    visited: set = set()
    while q:
        sid = q.popleft()
        if sid in visited:
            continue
        visited.add(sid)
        for cid in School.objects.filter(
            parent_school_id=sid, is_active=True
        ).values_list("pk", flat=True):
            collected.append(cid)
            q.append(cid)

    qs = School.objects.filter(pk__in=collected, is_active=True).order_by("name")
    if include_self:
        return (
            School.objects.filter(Q(pk=school.pk) | Q(pk__in=collected), is_active=True)
            .distinct()
            .order_by("name")
        )
    return qs


def get_school_tree(school) -> dict[str, Any]:
    """Nested dict for one level of children (deeper levels via recursion limit)."""
    if school is None:
        return {}
    School = _school_model()
    children = []
    for ch in (
        School.objects.filter(parent_school_id=school.pk, is_active=True)
        .order_by("name")
        .iterator()
    ):
        children.append(
            {
                "school": ch,
                "children": [  # one extra level only for compact UI
                    {"school": gc, "children": []}
                    for gc in School.objects.filter(
                        parent_school_id=ch.pk, is_active=True
                    ).order_by("name")
                ],
            }
        )
    return {"school": school, "children": children}


def _membership_role_sees_subtree(role: str) -> bool:
    r = (role or "").strip().upper()
    return r in _SUBTREE_MEMBERSHIP_ROLES


def _user_has_membership_for_school(user: "User", school_id) -> bool:
    from apps.schools.models import SchoolMembership

    return SchoolMembership.objects.filter(user_id=user.pk, school_id=school_id).exists()


def scoped_schools_for_user(user: "User", root_school=None) -> QuerySet:
    """
    Schools the user may operate on within optional ``root_school`` subtree.

    Fail-closed: without membership, returns empty queryset.
    """
    School = _school_model()
    if user is None or not getattr(user, "is_authenticated", False):
        return School.objects.none()

    from apps.schools.models import SchoolMembership

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    memberships = SchoolMembership.objects.filter(
        user=user, school__is_active=True
    ).select_related("school")
    ids: set = set()

    for m in memberships:
        sid = m.school_id
        role = getattr(m, "role", "") or ""
        ids.add(sid)
        if _membership_role_sees_subtree(role) or getattr(user, "is_superuser", False):
            desc = get_school_descendants(m.school, include_self=False)
            ids.update(desc.values_list("pk", flat=True))

    # Organization overlay (Phase 2): org roles see member schools in group mode.
    try:
        from apps.governance.models import OrgMembership
        from apps.governance.services import school_in_group_mode

        org_memberships = OrgMembership.objects.filter(user=user).select_related("organization")
        for org_membership in org_memberships:
            # tenant-isolation-allow: org-membership-scoped-school-list-for-group-operator
            org_schools = School.objects.filter(
                organization_id=org_membership.organization_id,
                is_active=True,
            )
            for org_school in org_schools:
                if school_in_group_mode(org_school):
                    ids.add(org_school.pk)
    except ImportError:
        pass

    if root_school is not None:
        allowed = {root_school.pk}
        allowed.update(get_school_descendants(root_school).values_list("pk", flat=True))
        ids = ids & allowed

    if not ids:
        return School.objects.none()
    return School.objects.filter(pk__in=ids, is_active=True).order_by("name")


def user_can_access_school_scope(user: "User", school, target_school) -> bool:
    """
    Whether ``user`` may load hierarchy/report context for ``target_school``
    while tenant context is ``school`` (typically ``request.school``).

    - Same school: allowed if membership or superuser staff on tenant.
    - Parent / descendant along same chain: allowed with rules below.
    - Siblings (same parent, different pk): denied unless superuser platform scope (still denied here — use impersonation).
    """
    from apps.schools.models import SchoolMembership

    if (
        user is None
        or not getattr(user, "is_authenticated", False)
        or school is None
        or target_school is None
    ):
        return False

    if target_school.pk == school.pk:
        return bool(
            getattr(user, "is_superuser", False)
            or SchoolMembership.objects.filter(user=user, school=school).exists()
        )

    if not SchoolMembership.objects.filter(user=user, school=school).exists() and not getattr(
        user, "is_superuser", False
    ):
        return False

    # Same hierarchy tree only
    root_a = school.get_root_school() or school
    root_b = target_school.get_root_school() or target_school
    if root_a.pk != root_b.pk:
        return False

    # Sibling denial (same parent, different campus)
    ps_self = school.parent_school_id
    ps_tgt = target_school.parent_school_id
    if (
        ps_self
        and ps_tgt
        and ps_self == ps_tgt
        and school.pk != target_school.pk
    ):
        return False

    # Target is ancestor of current → view-only up-tree allowed for staff on tenant
    ancestors_ids = {s.pk for s in get_school_ancestors(school)}
    if target_school.pk in ancestors_ids:
        return True

    # Target is descendant: subtree roles only
    if school.pk == target_school.parent_school_id or target_school.pk in get_school_descendants(
        school
    ).values_list("pk", flat=True):
        m = SchoolMembership.objects.filter(user=user, school=school).first()
        role = getattr(m, "role", "") if m else ""
        return _membership_role_sees_subtree(role) or getattr(user, "is_superuser", False)

    return False


def get_group_school_summary(root_school, user) -> Optional[dict[str, Any]]:
    """
    Read-only aggregate counts for campuses under ``root_school``.

    No fabricated analytics — only ORM counts where models exist. Permission enforced via
    ``scoped_schools_for_user``.
    """
    if root_school is None or user is None or not getattr(user, "is_authenticated", False):
        return None

    scoped = scoped_schools_for_user(user, root_school=None)
    scoped_ids = set(scoped.values_list("pk", flat=True))
    if root_school.pk not in scoped_ids:
        return None

    subtree_ids = [root_school.pk] + list(
        get_school_descendants(root_school).values_list("pk", flat=True)
    )
    allowed_ids = [pk for pk in subtree_ids if pk in scoped_ids]
    if not allowed_ids:
        return None

    summary: dict[str, Any] = {
        "campus_count": len(allowed_ids),
        "school_ids": allowed_ids,
        "student_count": None,
        "teacher_count": None,
        "report_schedule_count": None,
        "health_status_counts": {},
    }

    try:
        from apps.people.models import StudentProfile, TeacherProfile

        summary["student_count"] = StudentProfile.objects.filter(
            school_id__in=allowed_ids, is_active=True
        ).count()
        summary["teacher_count"] = TeacherProfile.objects.filter(
            school_id__in=allowed_ids, is_active=True
        ).count()
    except Exception:
        pass

    try:
        from apps.reports.models import TenantReportSchedule

        summary["report_schedule_count"] = TenantReportSchedule.objects.filter(
            school_id__in=allowed_ids
        ).count()
    except Exception:
        pass

    try:
        from apps.platform_runtime.customer_health import calculate_school_health

        buckets: dict[str, int] = {}
        School = _school_model()
        for sid in allowed_ids:
            sch = School.objects.filter(pk=sid).first()
            if not sch:
                continue
            h = calculate_school_health(sch)
            st = (h.get("status") or "unknown").strip() or "unknown"
            buckets[st] = buckets.get(st, 0) + 1
        summary["health_status_counts"] = buckets
    except Exception:
        summary["health_status_counts"] = {}

    return summary
