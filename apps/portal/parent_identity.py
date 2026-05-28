"""Parent identity UX helpers (CEZGP batches 1517 / 1521)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.platform_runtime.helpers import get_effective_flags


def resolve_parent_simplified_default(request: HttpRequest) -> bool:
    """
    Default simplified parent home via SiteSettings / runtime flags cascade.
    Query ``?simple=1`` forces on; ``?simple=0`` forces full dashboard.
    """
    flags = get_effective_flags(request)
    default_on = bool(flags.get("parent_simplified_default_home", True))
    raw = (request.GET.get("simple") or "").strip().lower()
    if raw in ("0", "false", "no", "full"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    return default_on


def school_membership_switch_context(request: HttpRequest) -> dict[str, Any]:
    """
    Multi-school guardian: expose membership count for portal chrome switcher.
    Actual switch UI uses ``components/rmc_campus_switcher.html`` + API.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {"school_membership_switch": {"enabled": False, "count": 0}}
    if str(getattr(user, "role", "") or "") != "PARENT":
        return {"school_membership_switch": {"enabled": False, "count": 0}}
    try:
        from apps.schools.models import SchoolMembership

        # tenant-isolation-allow: parent-membership-switch-user-scoped-multi-school
        count = SchoolMembership.objects.filter(
            user=user,
            school__is_active=True,
        ).count()
    except Exception:
        count = 0
    return {
        "school_membership_switch": {
            "enabled": count > 1,
            "count": count,
        }
    }


def guardian_student_links_chrome(request: HttpRequest) -> dict[str, Any]:
    """
    Top-bar quick links for linked students (CEZGP Lane 2 — P2).
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {"guardian_student_links_chrome": {"enabled": False, "links": []}}
    if str(getattr(user, "role", "") or "") != "PARENT":
        return {"guardian_student_links_chrome": {"enabled": False, "links": []}}
    try:
        from apps.portal.services import guardian_student_links

        qs = guardian_student_links(user, results_only=False)
        total = qs.count()
        links = []
        for row in qs[:4]:
            student = row.student
            label = (
                getattr(student, "full_name", None)
                or getattr(student, "name", None)
                or str(student)
            )
            links.append(
                {
                    "student_id": student.pk,
                    "label": str(label)[:24],
                }
            )
        return {
            "guardian_student_links_chrome": {
                "enabled": True,
                "links": links,
                "more_count": max(0, total - len(links)),
            }
        }
    except Exception:
        return {"guardian_student_links_chrome": {"enabled": False, "links": []}}


def parent_identity_portal_context(request: HttpRequest) -> dict[str, Any]:
    """Merged parent chrome context for portal_base (switcher + student links)."""
    ctx = school_membership_switch_context(request)
    ctx.update(guardian_student_links_chrome(request))
    return ctx
