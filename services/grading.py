"""
World Engine E.3: Service factory for cross-app grading logic.
Single entry point: get_grading_service(school) returns the grading implementation for the school type.
Use this from views/tasks; do not branch on school_type in views.
"""
from __future__ import annotations


def get_grading_service(school):
    """
    Return the grading service (module or class) for the given school.
    For TECHNICAL_COLLEGE (or from manifest) returns competency-based when implemented;
    else returns default academic grading (evals).
    """
    if school is None:
        return _default_grading_module()
    school_type = (getattr(school, "school_type", None) or "BASE_SCHOOL").strip().upper()
    if school_type == "TECHNICAL_COLLEGE":
        # When competency-based grading is implemented, return it here
        return _default_grading_module()
    return _default_grading_module()


def _default_grading_module():
    """Default academic grading (evals: coefficient-based average, mock blending, etc.)."""
    from apps.evals import ranking
    return ranking
