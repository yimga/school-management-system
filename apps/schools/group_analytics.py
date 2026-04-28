"""
Permission-aware group / multi-campus aggregates (no fabricated metrics).

Uses ``scoped_schools_for_user`` and subtree rules from ``hierarchy_helpers``.
"""

from __future__ import annotations

from typing import Any

from apps.schools.hierarchy_helpers import get_group_school_summary, scoped_schools_for_user


def get_group_attendance_summary(root_school, user) -> dict[str, Any] | None:
    """Count attendance rows for allowed subtree schools only (fail closed)."""
    base = get_group_school_summary(root_school, user)
    if base is None:
        return None
    ids = base.get("school_ids") or []
    if not ids:
        return {"total_rows": 0, "by_status": {}}
    try:
        from apps.academics.models import Attendance
        from django.db.models import Count

        qs = Attendance.objects.filter(school_id__in=ids)
        total = qs.count()
        by_status = dict(
            qs.values("status")
            .annotate(c=Count("id"))
            .values_list("status", "c")
        )
        return {"total_rows": total, "by_status": by_status}
    except Exception:  # noqa: BLE001
        return {"total_rows": None, "by_status": {}}


def get_group_report_summary(root_school, user) -> dict[str, Any] | None:
    """Report schedule rows in scope (reuses group school summary schedule count)."""
    base = get_group_school_summary(root_school, user)
    if base is None:
        return None
    return {
        "report_schedule_count": base.get("report_schedule_count"),
        "campus_count": base.get("campus_count"),
    }


def get_group_health_summary(root_school, user) -> dict[str, Any] | None:
    """Aggregate health status bucket counts from real per-school health (no fake score)."""
    base = get_group_school_summary(root_school, user)
    if base is None:
        return None
    return {
        "health_status_counts": base.get("health_status_counts") or {},
        "student_count": base.get("student_count"),
        "teacher_count": base.get("teacher_count"),
    }


def get_group_risk_signals(root_school, user) -> list[dict[str, Any]]:
    """
    Recent at-risk signal rows for students in allowed schools (capped); empty if none or no access.
    """
    if (
        root_school is None
        or user is None
        or not getattr(user, "is_authenticated", False)
    ):
        return []
    scoped_all = scoped_schools_for_user(user, root_school=None)
    if root_school.pk not in scoped_all.values_list("pk", flat=True):
        return []
    scoped = scoped_schools_for_user(user, root_school=root_school)
    allow = set(scoped.values_list("pk", flat=True))
    if not allow:
        return []
    try:
        from apps.analytics.models import StudentAtRiskSignal

        rows = StudentAtRiskSignal.objects.filter(school_id__in=allow).order_by(
            "-created_at"
        )[:25]
        return [
            {
                "id": str(x.pk),
                "school_id": str(x.school_id),
                "score": x.score,
                "status": x.status,
                "created_at": x.created_at.isoformat() if x.created_at else None,
            }
            for x in rows
        ]
    except Exception:  # noqa: BLE001
        return []


def build_group_intelligence_context(root_school, user) -> dict[str, Any]:
    """Single dict for templates (all subkeys may be None/empty when access denied)."""
    return {
        "group_school": get_group_school_summary(root_school, user),
        "attendance": get_group_attendance_summary(root_school, user),
        "reports": get_group_report_summary(root_school, user),
        "health": get_group_health_summary(root_school, user),
        "risk_signals": get_group_risk_signals(root_school, user),
    }
