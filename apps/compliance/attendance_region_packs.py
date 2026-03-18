"""
BR-05: Region-aware attendance compliance rules.
Resolved from School.default_region.code, optional school.settings['compliance_attendance_pack'] override.
Strict enforcement when school.features.live_compliance_attendance_strict is true.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

# Base packs by RegionConfig.code (primary key: CMR, USA, GBR, etc.)
REGION_ATTENDANCE_PACKS: dict[str, dict[str, Any]] = {
    "USA": {
        "key": "usa_attendance",
        "require_remarks_absent": True,
        "require_remarks_late": False,
        "min_remarks_len_absent": 3,
    },
    "GBR": {
        "key": "gbr_attendance",
        "require_remarks_absent": True,
        "require_remarks_late": True,
        "min_remarks_len_absent": 2,
    },
    "CAN": {
        "key": "can_attendance",
        "require_remarks_absent": True,
        "require_remarks_late": False,
        "min_remarks_len_absent": 2,
    },
    "AUS": {
        "key": "aus_attendance",
        "require_remarks_absent": True,
        "require_remarks_late": False,
        "min_remarks_len_absent": 2,
    },
    "CMR": {
        "key": "cmr_attendance",
        "require_remarks_absent": False,
        "require_remarks_late": False,
        "min_remarks_len_absent": 0,
    },
    "DEFAULT": {
        "key": "default_attendance",
        "require_remarks_absent": False,
        "require_remarks_late": False,
        "min_remarks_len_absent": 0,
    },
}


def _school_for_attendance(instance) -> Any:
    if getattr(instance, "school_id", None):
        return instance.school
    st = getattr(instance, "student", None)
    if st is not None and getattr(st, "school_id", None):
        return st.school
    return None


def get_resolved_attendance_pack(instance) -> dict[str, Any]:
    """Merge region defaults with school.settings.compliance_attendance_pack."""
    school = _school_for_attendance(instance)
    base = dict(REGION_ATTENDANCE_PACKS["DEFAULT"])
    if school:
        reg = getattr(school, "default_region", None)
        code = getattr(reg, "pk", None) or getattr(reg, "code", None)
        if code and str(code) in REGION_ATTENDANCE_PACKS:
            base = {**base, **REGION_ATTENDANCE_PACKS[str(code)]}
        elif code:
            base = {**base, "key": f"region_{code}", "require_remarks_absent": False}
        ov = (getattr(school, "settings", None) or {}).get("compliance_attendance_pack")
        if isinstance(ov, dict):
            base = {**base, **ov}
    return base


def attendance_compliance_errors(instance) -> dict[str, str]:
    """
    Field errors for Attendance instance (before save). Empty if no violations.
    Uses live_compliance_attendance_strict on school.features.
    """
    from apps.academics.models import Attendance

    school = _school_for_attendance(instance)
    if not school:
        return {}
    feats = getattr(school, "features", None) or {}
    if not feats.get("live_compliance_attendance_strict"):
        return {}
    pack = get_resolved_attendance_pack(instance)
    remarks = (getattr(instance, "remarks", None) or "").strip()
    errors: dict[str, str] = {}
    st = instance.status
    if pack.get("require_remarks_absent") and st == Attendance.Status.ABSENT:
        min_len = int(pack.get("min_remarks_len_absent") or 1)
        if len(remarks) < min_len:
            errors["remarks"] = str(
                _(
                    "Reason for absence is required (minimum %(n)s characters) for your region."
                )
                % {"n": min_len}
            )
    if pack.get("require_remarks_late") and st == Attendance.Status.LATE:
        if len(remarks) < 1:
            errors["remarks"] = str(
                _("Reason for lateness is required for your region.")
            )
    return errors


def should_enforce_strict_block(instance) -> bool:
    school = _school_for_attendance(instance)
    if not school:
        return False
    return bool(
        (getattr(school, "features", None) or {}).get(
            "live_compliance_attendance_strict"
        )
    )
