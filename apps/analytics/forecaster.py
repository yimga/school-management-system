"""
Phase Welcome (optional): Academic Forecaster — anonymized indicators, at-risk hint, principal forecast.
No PII leaves tenant schema; all aggregation is in-tenant or from anonymized benchmarks.
"""
from __future__ import annotations

from typing import Any


def get_anonymized_indicators(school) -> dict[str, Any]:
    """
    Return anonymized comparison indicators for the tenant (e.g. attendance vs benchmark).
    No student-level PII. Benchmarks can be from GlobalIndicator or fixed placeholders.
    """
    if school is None:
        return {"attendance_rate_avg": None, "national_benchmark": None, "above_benchmark": None}
    from apps.people.models import StudentProfile
    student_count = StudentProfile.objects.filter(school=school, is_active=True).count()
    # Placeholder benchmark (replace with GlobalIndicator / national average when available)
    national_benchmark = 0.82
    attendance_avg = None  # computed from tenant data when available
    above = attendance_avg is not None and attendance_avg >= national_benchmark
    return {
        "attendance_rate_avg": attendance_avg,
        "national_benchmark": national_benchmark,
        "above_benchmark": above,
        "student_count": student_count,
    }


def at_risk_hint(school) -> dict[str, Any]:
    """
    At-risk flag: count of students below threshold (e.g. attendance < 80% of benchmark).
    Returns anonymized count and threshold; no PII.
    """
    if school is None:
        return {"count": 0, "threshold_note": "attendance_below_80", "enabled": False}
    # Placeholder: when attendance + benchmark exist, count students below threshold
    return {"count": 0, "threshold_note": "attendance_below_80", "enabled": True}


def principal_forecast_teachers(school, *, target_ratio: float = 25.0) -> dict[str, Any]:
    """
    Principal forecast: suggested FTE teachers from enrollment and student–teacher ratio.
    No PII; tenant-scoped counts only.
    """
    if school is None:
        return {"suggested_fte": 0, "student_count": 0, "ratio": target_ratio}
    from apps.people.models import StudentProfile, TeacherProfile
    students = StudentProfile.objects.filter(school=school, is_active=True).count()
    teachers = TeacherProfile.objects.filter(school=school).count()
    import math
    suggested = max(0, math.ceil(students / target_ratio) if target_ratio else 0)
    return {
        "student_count": students,
        "current_teachers": teachers,
        "suggested_fte": suggested,
        "ratio": target_ratio,
        "gap": suggested - teachers,
    }
