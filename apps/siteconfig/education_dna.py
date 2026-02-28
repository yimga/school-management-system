"""
Universal Education OS (XXI): Education DNA JSON — polymorphic academic groups.
Return country/system-specific curriculums (terms, grading, terminology) for
injection into tenant config. Persist or derive from EducationSystemProfile.config / RegionConfig.
"""
from __future__ import annotations

from typing import Any

# Built-in Education DNA template (plan XXI). Keys match preset names for Apply Template.
EDUCATION_DNA_CURRICULUMS = {
    "british_igcse": {
        "terms": ["Michaelmas", "Lent", "Trinity"],
        "grading": {"type": "letter", "scale": ["A*", "A", "B", "C", "D", "E", "F", "G"]},
        "weighting": "Summative",
    },
    "west_african_waec": {
        "terms": ["First", "Second", "Third"],
        "grading": {"type": "alphanumeric", "scale": ["A1", "B2", "B3", "C4", "C5", "C6", "D7", "E8", "F9"]},
        "weighting": {"CA": 0.3, "Exam": 0.7},
    },
    "francophone_bac": {
        "terms": ["Trimestre 1", "Trimestre 2", "Trimestre 3"],
        "grading": {"type": "numeric", "max": 20, "passing": 10},
        "terminology": {"teacher": "Enseignant", "grade": "Note", "average": "Moyenne"},
    },
    "american": {
        "terms": ["Fall", "Spring"],
        "grading": {"type": "gpa", "max": 4.0},
        "weighting": "credit_hour",
    },
}


def get_education_dna(school=None, region_code: str | None = None) -> dict[str, Any]:
    """
    Return Education DNA structure: { "curriculums": { ... } }.
    Used for locale-aware middleware and polymorphic academic behaviour.
    If school is provided, prefer its default_region or settings; else use region_code.
    """
    code = None
    if school:
        if getattr(school, "default_region_id", None):
            try:
                from apps.siteconfig.models import RegionConfig
                r = RegionConfig.objects.filter(pk=school.default_region_id).first()
                if r:
                    code = getattr(r, "code", None)
            except Exception:
                pass
        if not code and isinstance(getattr(school, "settings", None), dict):
            code = (school.settings or {}).get("education_dna_preset")
    code = code or region_code or "british_igcse"
    preset = EDUCATION_DNA_CURRICULUMS.get(code) or EDUCATION_DNA_CURRICULUMS.get("british_igcse", {})
    return {"curriculums": {code: preset}}
