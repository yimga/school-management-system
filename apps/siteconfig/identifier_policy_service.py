"""
Section 22: Identifier policy service for tenant admission number generation and validation.
Uses TenantAdmissionNumberPolicy when present, else get_effective_policy(school)["admissions"] / SiteSettings.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from django.db import DatabaseError


OPTIONAL_POLICY_ERRORS = (AttributeError, DatabaseError, ImportError, TypeError, ValueError)


def default_school_code_for(school=None, fallback: str = "SCH") -> str:
    raw = (getattr(school, "slug", None) or getattr(school, "name", None) or "").strip().upper()
    if not raw:
        return fallback
    parts = [part for part in re.split(r"[^A-Z0-9]+", raw) if part]
    initials = "".join(part[0] for part in parts[:6])
    if initials:
        return initials[:6]
    return "".join(parts)[:6] or fallback


def get_admissions_policy(school) -> Dict[str, Any]:
    """
    Return merged admission number config for a school.
    TenantAdmissionNumberPolicy overrides when present and active; else policy resolver + SiteSettings.
    """
    try:
        from apps.siteconfig.models import TenantAdmissionNumberPolicy
        if school is None:
            raise ValueError("school required")
        policy_model = TenantAdmissionNumberPolicy.objects.filter(school=school, is_active=True).first()
        if policy_model:
            template = (getattr(policy_model, "template", None) or "").strip()
            return {
                "school_code": (getattr(policy_model, "school_code", None) or default_school_code_for(school)).upper(),
                "admission_number_strategy": getattr(policy_model, "strategy", "FULL") or "FULL",
                "admission_number_template": template,
                "admission_number_pattern": (getattr(policy_model, "pattern", None) or "").strip(),
                "admission_number_mode": "AUTO_OR_MANUAL",
                "seq_width": getattr(policy_model, "seq_width", 4),
                "reset_frequency": getattr(policy_model, "reset_frequency", "YEARLY"),
            }
    except OPTIONAL_POLICY_ERRORS:
        pass
    from apps.policies.policy_registry import get_effective_policy
    out = get_effective_policy(school)
    return out.get("admissions") or {}


def preview_admission_number(
    school,
    *,
    year_2digit: str = "26",
    school_code: str = "",
    seq_4digit: str = "0001",
    spec_code: str = "XX",
    class_segment: str = "00",
) -> str:
    """
    Section 22.2: Return a sample admission number for the given policy (for setup preview).
    """
    policy = get_admissions_policy(school)
    school_code = (school_code or policy.get("school_code") or default_school_code_for(school)).upper()
    template = (policy.get("admission_number_template") or "").strip()
    if template:
        try:
            return template.format(
                year_2digit=year_2digit,
                school_code=school_code,
                seq_4digit=seq_4digit,
                spec_code=spec_code,
                class_segment=class_segment,
            )
        except KeyError:
            pass
    strategy = policy.get("admission_number_strategy") or "FULL"
    if strategy == "YEAR_SEQ":
        return f"{year_2digit}{school_code}{seq_4digit}"
    if strategy == "SEQ_ONLY":
        return seq_4digit
    return f"{year_2digit}{school_code}{seq_4digit}{spec_code}{class_segment}"


def validate_admission_number(school, value: str) -> bool:
    """Return True if value matches the policy pattern for this school."""
    if not value or not value.strip():
        return True
    policy = get_admissions_policy(school)
    pattern = (policy.get("admission_number_pattern") or "").strip()
    if not pattern:
        pattern = r"^(\d{2}[A-Z0-9]{2,10}\d{4}[A-Z0-9]{2,6}[A-Z0-9]{1,4})|(\d{2}-[A-Z0-9]{2,10}-\d{4}-[A-Z0-9]{2,6}-[A-Z0-9]{1,4})$"
    try:
        return bool(re.match(pattern, value.strip()))
    except re.error:
        return True
