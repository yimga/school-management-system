"""
North Star SLICE 4 — tenant-aware terminology (defaults → curriculum template → tenant override).

Tenant storage (School.settings JSON, no migration):

- ``curriculum_template_key``: optional string matching SLICE 3 registry keys.
- ``terminology``: optional partial dict with keys ``grade``, ``gpa``, ``term``, ``report_card``.
"""

from __future__ import annotations

from typing import Any

from apps.siteconfig.curriculum_templates_service import get_template_terminology

# Canonical keys aligned with curriculum_templates_registry terminology_map
TERMINOLOGY_KEYS = frozenset({"grade", "gpa", "term", "report_card"})

DEFAULT_TERMINOLOGY: dict[str, str] = {
    "grade": "Grade",
    "gpa": "GPA",
    "term": "Term",
    "report_card": "Report card",
}


def _school_settings_dict(school: Any) -> dict[str, Any]:
    raw = getattr(school, "settings", None)
    return raw if isinstance(raw, dict) else {}


def get_effective_terminology_for_school(school: Any) -> dict[str, str]:
    """
    Resolve terminology: defaults, then curriculum template (if key set), then tenant overrides.
    Non-empty override strings win per key.
    """
    merged = dict(DEFAULT_TERMINOLOGY)
    if school is None:
        return merged

    raw = _school_settings_dict(school)

    tk = (raw.get("curriculum_template_key") or "").strip()
    if tk:
        tmpl_map = get_template_terminology(tk)
        for key in TERMINOLOGY_KEYS:
            val = tmpl_map.get(key)
            if val is not None and str(val).strip():
                merged[key] = str(val).strip()

    overrides = raw.get("terminology")
    if isinstance(overrides, dict):
        for key in TERMINOLOGY_KEYS:
            if key not in overrides:
                continue
            val = overrides.get(key)
            if val is None:
                continue
            sval = str(val).strip()
            if sval:
                merged[key] = sval

    return merged


def describe_terminology_resolution(school: Any) -> str:
    """Human-readable provenance for operator UI (preview only)."""
    if school is None:
        return "defaults"
    raw = _school_settings_dict(school)
    tk = (raw.get("curriculum_template_key") or "").strip()
    ov = raw.get("terminology") if isinstance(raw.get("terminology"), dict) else {}
    has_ov = any(
        ov.get(k) and str(ov.get(k) or "").strip() for k in TERMINOLOGY_KEYS
    )
    if tk and has_ov:
        return f"curriculum template ({tk}) + tenant terminology override"
    if has_ov:
        return "tenant terminology override"
    if tk:
        return f"curriculum template ({tk})"
    return "product defaults"


def get_grade_label(school: Any) -> str:
    return get_effective_terminology_for_school(school)["grade"]


def get_gpa_label(school: Any) -> str:
    return get_effective_terminology_for_school(school)["gpa"]


def get_term_label(school: Any) -> str:
    return get_effective_terminology_for_school(school)["term"]


def get_report_label(school: Any) -> str:
    return get_effective_terminology_for_school(school)["report_card"]


__all__ = [
    "DEFAULT_TERMINOLOGY",
    "TERMINOLOGY_KEYS",
    "describe_terminology_resolution",
    "get_effective_terminology_for_school",
    "get_grade_label",
    "get_gpa_label",
    "get_report_label",
    "get_term_label",
]
