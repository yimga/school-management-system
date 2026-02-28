"""
Rosetta Stone: cross-tenant / cross-system grade conversion API.

Converts grades between scales (e.g. Francophone 16/20 -> US GPA 3.2 / B+)
using a normalized 0.0-1.0 anchor. Used for frictionless global student mobility.
"""

from decimal import Decimal
from typing import Optional

from apps.evals.grading import (
    GRADING_SCALES,
    convert_score,
    get_grade_letter,
    get_scale_for_school,
    score_to_normalized,
)


# Scale identifiers used by grading.py
SCALE_IDS = list(GRADING_SCALES.keys())  # e.g. '0-20', '0-100', '0-10', 'a-f', 'gpa'


def normalize_score(score: float, school=None) -> Optional[Decimal]:
    """Convert a raw score to normalized 0.0-1.0 for the given school's scale."""
    if score is None:
        return None
    return score_to_normalized(score, school)


def convert_grade(
    score: float,
    from_scale: Optional[str] = None,
    to_scale: Optional[str] = None,
    school=None,
) -> dict:
    """
    Convert a score from one grading scale to another (Rosetta Stone).
    Uses school's scale as from_scale when school is provided and from_scale is None.

    Returns dict with: converted_score, normalized_value, letter_grade (when to_scale supports it).
    """
    if from_scale is None and school is not None:
        from_scale = get_scale_for_school(school)
    from_scale = from_scale or "0-20"
    to_scale = to_scale or "0-20"
    if from_scale not in GRADING_SCALES:
        from_scale = "0-20"
    if to_scale not in GRADING_SCALES:
        to_scale = "0-20"

    converted = convert_score(Decimal(str(score)), from_scale, to_scale)
    fc = GRADING_SCALES[from_scale]
    mn, mx = fc["min"], fc["max"]
    if mx == mn:
        normalized = Decimal("0")
    else:
        normalized = (Decimal(str(score)) - mn) / (mx - mn)
        normalized = max(Decimal("0"), min(Decimal("1"), normalized))

    result = {
        "from_scale": from_scale,
        "to_scale": to_scale,
        "raw_score": float(score),
        "converted_score": float(converted),
        "normalized_value": float(normalized.quantize(Decimal("0.0001"))),
    }
    try:
        result["letter_grade"] = get_grade_letter(float(converted), to_scale)
    except Exception:
        result["letter_grade"] = None
    return result


def get_supported_scales() -> list:
    """Return list of scale ids supported for conversion."""
    return list(GRADING_SCALES.keys())
