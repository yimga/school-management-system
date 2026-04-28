"""
DB-driven grading scale resolution and band lookup (North Star SLICE 2).

Does not replace ``apps.evals.grading`` / ``rosetta_stone`` linear conversions; extends
tenant configuration with explicit band tables when present.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.schools.models import School
    from apps.evals.models import GradingScale, GradingScaleBand


def get_effective_grading_scale_for_school(school: Optional["School"]):
    """
    Return the active tenant GradingScale for this school, or None.

    Preference: is_default=True, then first active by name.
    """
    if school is None:
        return None
    from apps.evals.models import GradingScale

    base = GradingScale.objects.filter(
        school=school,
        is_active=True,
    )
    default = base.filter(is_default=True).order_by("name").first()
    if default:
        return default
    return base.order_by("name").first()


def get_scale_bands_ordered(scale: Optional["GradingScale"]) -> list:
    """Return bands for a scale, ordered for display."""
    if scale is None:
        return []
    return list(
        scale.bands.all().order_by("sort_order", "min_score", "pk")
    )


def get_grade_band_for_score(
    scale: Optional["GradingScale"],
    score: Any,
) -> Optional["GradingScaleBand"]:
    """Map a raw score to the first matching band (inclusive min/max)."""
    if scale is None or score is None:
        return None
    try:
        s = Decimal(str(score))
    except (ArithmeticError, TypeError, ValueError):
        return None
    for band in get_scale_bands_ordered(scale):
        if band.min_score <= s <= band.max_score:
            return band
    return None


def get_grade_band_for_normalized(
    scale: Optional["GradingScale"],
    normalized_value: Any,
) -> Optional["GradingScaleBand"]:
    """Map a Rosetta normalized 0.0–1.0 value to a band."""
    return convert_normalized_to_band(scale, normalized_value)


def convert_normalized_to_band(
    scale: Optional["GradingScale"],
    normalized_value: Any,
) -> Optional["GradingScaleBand"]:
    if scale is None or normalized_value is None:
        return None
    try:
        n = Decimal(str(normalized_value))
    except (ArithmeticError, TypeError, ValueError):
        return None
    n = max(Decimal("0"), min(Decimal("1"), n))
    for band in get_scale_bands_ordered(scale):
        if band.normalized_min <= n <= band.normalized_max:
            return band
    return None


__all__ = [
    "convert_normalized_to_band",
    "get_effective_grading_scale_for_school",
    "get_grade_band_for_normalized",
    "get_grade_band_for_score",
    "get_scale_bands_ordered",
]
