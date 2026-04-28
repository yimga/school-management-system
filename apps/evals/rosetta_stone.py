"""
Rosetta Stone: cross-tenant / cross-system grade conversion API.

Converts grades between scales (e.g. Francophone 16/20 -> US GPA 3.2 / B+)
using a normalized 0.0-1.0 anchor. Used for frictionless global student mobility.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from apps.evals.grading import (
    GRADING_SCALES,
    convert_score,
    format_score,
    get_grade_letter,
    get_scale_for_school,
    score_to_normalized,
)


logger = logging.getLogger(__name__)

# Typed exceptions for get_grade_letter (scale lookup / conversion).
_EVALS_ROSETTA_LETTER_GRADE_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    InvalidOperation,
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
    except _EVALS_ROSETTA_LETTER_GRADE_ERRORS as e:
        logger.debug(
            "evals.rosetta_stone: get_grade_letter failed for to_scale=%s: %s",
            to_scale,
            e,
        )
        result["letter_grade"] = None
    return result


def get_supported_scales() -> list:
    """Return list of scale ids supported for conversion."""
    return list(GRADING_SCALES.keys())


def _sanitize_scale_id(scale: Optional[str], *, default: str = "0-100") -> str:
    s = (scale or default).strip()
    if s not in GRADING_SCALES:
        return default if default in GRADING_SCALES else "0-20"
    return s


def normalized_to_target_score(
    normalized: Optional[object], to_scale: Optional[str] = "0-100"
) -> Optional[Decimal]:
    """
    Map a stored 0.0–1.0 normalized value to a score on the target scale (linear).
    Used when `Evaluation.normalized_value` is present for stable cross-system display.
    """
    if normalized is None:
        return None
    to_id = _sanitize_scale_id(to_scale, default="0-100")
    cfg = GRADING_SCALES[to_id]
    try:
        n = Decimal(str(normalized))
    except (InvalidOperation, TypeError, ValueError):
        return None
    n = max(Decimal("0"), min(Decimal("1"), n))
    mn, mx = cfg["min"], cfg["max"]
    if mx == mn:
        return mn
    return (n * (mx - mn) + mn).quantize(Decimal("0.01"))


def view_grade_in_target_system(
    evaluation: object,
    to_scale: Optional[str] = "0-100",
    *,
    prefer_stored_normalization: bool = True,
) -> dict:
    """
    Report/API helper: show how this evaluation reads in a target grading system.

    Prefer persisted ``normalized_value`` when set and ``prefer_stored_normalization`` is True,
    so display stays aligned with stored Rosetta data; otherwise convert from ``final_score``
    using the tenant scale from ``get_scale_for_school(evaluation.school)``.
    """
    to_id = _sanitize_scale_id(to_scale, default="0-100")
    school = getattr(evaluation, "school", None)
    from_id = get_scale_for_school(school)

    stored_norm = getattr(evaluation, "normalized_value", None)
    final = getattr(evaluation, "final_score", None)
    if final is None and stored_norm is None:
        return {
            "ok": False,
            "reason": "no_score",
            "to_scale": to_id,
            "from_scale": from_id,
        }

    use_stored = bool(
        prefer_stored_normalization and stored_norm is not None
    )
    if use_stored:
        conv = normalized_to_target_score(stored_norm, to_id)
        if conv is None:
            return {
                "ok": False,
                "reason": "conversion_failed",
                "to_scale": to_id,
                "from_scale": from_id,
            }
        conv_f = float(conv)
        norm_for_out = float(stored_norm) if stored_norm is not None else None
    else:
        if final is None:
            return {
                "ok": False,
                "reason": "no_score",
                "to_scale": to_id,
                "from_scale": from_id,
            }
        try:
            raw = float(final)
        except (TypeError, ValueError, InvalidOperation):
            return {
                "ok": False,
                "reason": "invalid_final_score",
                "to_scale": to_id,
                "from_scale": from_id,
            }
        cg = convert_grade(raw, from_id, to_id, school=school)
        conv_f = float(cg["converted_score"])
        if stored_norm is not None:
            norm_for_out = float(stored_norm)
        else:
            try:
                norm_for_out = float(cg.get("normalized_value", 0.0) or 0.0)
            except (TypeError, ValueError):
                norm_for_out = None

    letter = None
    try:
        letter = get_grade_letter(conv_f, to_id)
    except _EVALS_ROSETTA_LETTER_GRADE_ERRORS:
        letter = None
    try:
        display = format_score(conv_f, to_id)
    except (TypeError, ValueError, KeyError, InvalidOperation, ZeroDivisionError):
        try:
            display = f"{conv_f:.2f}"
        except (TypeError, ValueError):
            display = "—"
    if letter:
        display = f"{display} ({letter})" if display else str(letter)

    return {
        "ok": True,
        "to_scale": to_id,
        "from_scale": from_id,
        "used_stored_normalized": use_stored,
        "normalized_value": norm_for_out,
        "converted_score": conv_f,
        "letter_grade": letter,
        "display": display,
    }


def format_rosetta_line(
    evaluation: object, to_scale: Optional[str] = "0-100", **kwargs
) -> str:
    """One-line string for templates: target scale label + converted value, or em dash if N/A."""
    v = view_grade_in_target_system(evaluation, to_scale, **kwargs)
    if not v.get("ok"):
        return "—"
    return v.get("display") or "—"
