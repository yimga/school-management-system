"""
BR-05: Region-aware degree-enrollment compliance (StudentDegreeEnrollment).
Mirrors attendance_region_packs: pack from School.default_region + optional
school.settings['compliance_enrollment_pack'] override.

Strict: school.features.live_compliance_enrollment_strict → ValidationError on save.
Audit: school.features.live_compliance_enrollment → PlatformEventLog on soft violations.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

REGION_ENROLLMENT_PACKS: dict[str, dict[str, Any]] = {
    "USA": {
        "key": "usa_enrollment",
        "require_start_date_when_active": True,
    },
    "GBR": {
        "key": "gbr_enrollment",
        "require_start_date_when_active": True,
    },
    "CAN": {
        "key": "can_enrollment",
        "require_start_date_when_active": True,
    },
    "AUS": {
        "key": "aus_enrollment",
        "require_start_date_when_active": True,
    },
    "CMR": {
        "key": "cmr_enrollment",
        "require_start_date_when_active": False,
    },
    "DEFAULT": {
        "key": "default_enrollment",
        "require_start_date_when_active": False,
    },
}


def _school_for_enrollment(instance) -> Any:
    st = getattr(instance, "student", None)
    if st is not None and getattr(st, "school_id", None):
        return st.school
    return None


def get_resolved_enrollment_pack(instance) -> dict[str, Any]:
    school = _school_for_enrollment(instance)
    base = dict(REGION_ENROLLMENT_PACKS["DEFAULT"])
    if school:
        reg = getattr(school, "default_region", None)
        code = getattr(reg, "pk", None) or getattr(reg, "code", None)
        if code and str(code) in REGION_ENROLLMENT_PACKS:
            base = {**base, **REGION_ENROLLMENT_PACKS[str(code)]}
        elif code:
            base = {
                **base,
                "key": f"region_{code}",
                "require_start_date_when_active": False,
            }
        ov = (getattr(school, "settings", None) or {}).get("compliance_enrollment_pack")
        if isinstance(ov, dict):
            base = {**base, **ov}
    return base


def enrollment_compliance_errors(instance) -> dict[str, str]:
    """Field errors before save when strict enforcement is on."""
    school = _school_for_enrollment(instance)
    if not school:
        return {}
    feats = getattr(school, "features", None) or {}
    if not feats.get("live_compliance_enrollment_strict"):
        return {}
    pack = get_resolved_enrollment_pack(instance)
    errors: dict[str, str] = {}
    active = bool(getattr(instance, "is_active", True))
    if pack.get("require_start_date_when_active") and active:
        if getattr(instance, "start_date", None) is None:
            errors["start_date"] = str(
                _(
                    "Program start date is required for active enrollments in your region."
                )
            )
    return errors


def should_enforce_enrollment_strict_block(instance) -> bool:
    school = _school_for_enrollment(instance)
    if not school:
        return False
    return bool(
        (getattr(school, "features", None) or {}).get(
            "live_compliance_enrollment_strict"
        )
    )


def enrollment_soft_compliance_issues(instance) -> list[str]:
    """Non-blocking issues for audit log (when live_compliance_enrollment, not strict)."""
    school = _school_for_enrollment(instance)
    if not school:
        return []
    pack = get_resolved_enrollment_pack(instance)
    issues: list[str] = []
    active = bool(getattr(instance, "is_active", True))
    if (
        pack.get("require_start_date_when_active")
        and active
        and getattr(instance, "start_date", None) is None
    ):
        issues.append("active_enrollment_missing_start_date")
    return issues
