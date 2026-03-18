"""
BR-05: Validate-on-write for enrollment-related payloads when live compliance is enabled.
Enable per school: set settings['compliance_live_validation'] on the School record.
"""

from __future__ import annotations

from typing import Any


def live_compliance_enrollment_errors(school, payload: dict[str, Any]) -> list[str]:
    """
    Return user-facing error strings if validation fails; empty if OK or feature off.
    """
    if school is None:
        return []
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        return []
    if not settings.get("compliance_live_validation"):
        return []
    errs: list[str] = []
    if not (payload.get("enrollment_date") or payload.get("start_date")):
        errs.append(
            "enrollment_date (or start_date) is required when live compliance validation is enabled for this school."
        )
    if payload.get("student_id") in (None, "") and payload.get("student_user_id") in (
        None,
        "",
    ):
        errs.append("student reference is required for enrollment records.")
    return errs


def live_compliance_attendance_errors(school, payload: dict[str, Any]) -> list[str]:
    if school is None:
        return []
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict) or not settings.get("compliance_live_validation"):
        return []
    errs: list[str] = []
    if not payload.get("session_date") and not payload.get("date"):
        errs.append(
            "session date is required when live compliance validation is enabled."
        )
    if not payload.get("status") and not payload.get("attendance_code"):
        errs.append("attendance status or code is required.")
    return errs
