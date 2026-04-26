"""
Lightweight tenant health from real counts and onboarding progress (no external analytics).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_STATUS_SETUP = "setup_needed"
_STATUS_AT_RISK = "at_risk"
_STATUS_HEALTHY = "healthy"
_STATUS_POWER = "power_user"


def calculate_school_health(school) -> dict[str, Any]:
    """Return score 0–100 and status enum from tenant data."""
    if school is None:
        return {
            "score": 0,
            "status": _STATUS_SETUP,
            "onboarding_percent": 0,
            "student_count": 0,
            "teacher_count": 0,
            "has_report_schedules": False,
        }

    from apps.platform_runtime.onboarding import get_school_onboarding_progress

    prog = get_school_onboarding_progress(school)
    pct = int(prog.get("percent") or 0)

    student_count = 0
    teacher_count = 0
    has_report_schedules = False
    try:
        from apps.people.models import StudentProfile, TeacherProfile

        student_count = StudentProfile.objects.filter(
            school_id=school.id, is_active=True
        ).count()
        teacher_count = TeacherProfile.objects.filter(school_id=school.id).count()
    except Exception as ex:  # noqa: BLE001
        logger.debug("customer_health people counts: %s", ex)
    try:
        from apps.reports.models import TenantReportSchedule

        has_report_schedules = TenantReportSchedule.objects.filter(
            school_id=school.id
        ).exists()
    except Exception as ex:  # noqa: BLE001
        logger.debug("customer_health reports: %s", ex)

    # Score blends activation progress with light usage depth (capped, transparent).
    depth = 0.0
    if student_count:
        depth += min(30.0, 30.0 * (1 - pow(0.99, min(student_count, 500))))
    if teacher_count:
        depth += min(20.0, 20.0 * (1 - pow(0.92, min(teacher_count, 40))))
    if has_report_schedules:
        depth += 10.0
    base = min(100.0, float(pct) * 0.5 + depth)
    score = int(max(0, min(100, round(base))))

    if pct < 30 or student_count < 1:
        status = _STATUS_SETUP
    elif pct < 70 or not has_report_schedules or student_count < 3:
        status = _STATUS_AT_RISK
    elif pct >= 90 and student_count >= 30 and teacher_count >= 4:
        status = _STATUS_POWER
    else:
        status = _STATUS_HEALTHY

    return {
        "score": score,
        "status": status,
        "onboarding_percent": pct,
        "student_count": student_count,
        "teacher_count": teacher_count,
        "has_report_schedules": has_report_schedules,
    }


def get_school_health_recommendations(
    school, user: Optional[Any] = None, limit: int = 4
) -> list[dict[str, str]]:
    """Short actionable nudges with real URLs; empty if nothing to say."""
    del user
    if school is None:
        return []
    from apps.platform_runtime.onboarding import get_school_onboarding_steps

    out: list[dict[str, str]] = []
    for row in get_school_onboarding_steps(school):
        if row.get("done"):
            continue
        link = (row.get("link") or "").strip()
        if not link:
            continue
        out.append(
            {
                "label": str(row.get("label") or "Next step"),
                "url": link,
                "key": str(row.get("key") or ""),
            }
        )
        if len(out) >= int(limit):
            break
    return out
