"""
Universal Education OS (XXI): Education DNA JSON — polymorphic academic groups.
Return country/system-specific curriculums (terms, grading, terminology) for
injection into tenant config. Persist or derive from EducationSystemProfile.config / RegionConfig.
"""

from __future__ import annotations

from typing import Any

from django.db import DatabaseError

from apps.global_registries.models import RegionConfig

# Built-in Education DNA template (plan XXI). Keys match preset names for Apply Template.
EDUCATION_DNA_CURRICULUMS = {
    "british_igcse": {
        "terms": ["Michaelmas", "Lent", "Trinity"],
        "grading": {
            "type": "letter",
            "scale": ["A*", "A", "B", "C", "D", "E", "F", "G"],
        },
        "weighting": "Summative",
    },
    "west_african_waec": {
        "terms": ["First", "Second", "Third"],
        "grading": {
            "type": "alphanumeric",
            "scale": ["A1", "B2", "B3", "C4", "C5", "C6", "D7", "E8", "F9"],
        },
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
    "vocational": {
        "terms": ["Block 1", "Block 2", "Block 3"],
        "grading": {"type": "competency", "scale": ["Competent", "Not yet competent"]},
        "weighting": "clock_hours",
        "terminology": {
            "teacher": "Instructor",
            "grade": "Assessment",
            "average": "Completion",
        },
    },
    "ib": {
        "terms": ["Year 1", "Year 2"],
        "grading": {"type": "numeric", "scale": [7, 6, 5, 4, 3, 2, 1], "passing": 4},
        "weighting": "Summative",
        "terminology": {"teacher": "Teacher", "grade": "Grade", "average": "Predicted"},
    },
    "east_asia_competitive": {
        "terms": ["Term 1", "Term 2"],
        "grading": {
            "type": "standard_score",
            "scale_max": 100,
            "ranking_mode": "standard_score_t",
        },
        "weighting": {"CA": 0.3, "Exam": 0.7},
        "terminology": {"teacher": "Teacher", "grade": "Score", "average": "Mean"},
    },
}

# Map uppercase template codes (API/super_views) to EDUCATION_DNA_CURRICULUMS keys.
EDUCATION_DNA_CODE_ALIASES = {
    "BRITISH_IGCSE": "british_igcse",
    "WAEC": "west_african_waec",
    "FRANCOPHONE_BAC": "francophone_bac",
    "VOCATIONAL": "vocational",
    "AMERICAN": "american",
    "IB": "ib",
    "EAST_ASIA": "east_asia_competitive",
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
                r = RegionConfig.objects.filter(pk=school.default_region_id).first()
                if r:
                    code = getattr(r, "code", None)
            except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
                pass
        if not code:
            try:
                from apps.policies.policy_registry import get_effective_policy

                code = get_effective_policy(school).get("education_dna_preset")
            except (AttributeError, DatabaseError, ImportError, TypeError, ValueError):
                pass
    code = code or region_code or "british_igcse"
    code = EDUCATION_DNA_CODE_ALIASES.get(code, code) if isinstance(code, str) else code
    preset = EDUCATION_DNA_CURRICULUMS.get(code) or EDUCATION_DNA_CURRICULUMS.get(
        "british_igcse", {}
    )
    return {"curriculums": {code: preset}}
