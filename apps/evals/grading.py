"""
Grading utilities for Phase 1.2.4: Internationalization & Multi-Region Support

Provides score conversion, formatting, and grade calculation functions
for multiple grading scales across different regions.
"""

from decimal import Decimal
from django.core.cache import cache


# Global grading scale definitions
GRADING_SCALES = {
    "0-20": {
        "min": Decimal("0"),
        "max": Decimal("20"),
        "grades": {
            "A": Decimal("18"),
            "B": Decimal("15"),
            "C": Decimal("12"),
            "D": Decimal("9"),
            "F": Decimal("0"),
        },
        "display": lambda score: f"{score:.0f}/20",
    },
    "0-100": {
        "min": Decimal("0"),
        "max": Decimal("100"),
        "grades": {
            "A": Decimal("90"),
            "B": Decimal("80"),
            "C": Decimal("70"),
            "D": Decimal("60"),
            "F": Decimal("0"),
        },
        "display": lambda score: f"{score:.0f}%",
    },
    "0-10": {
        "min": Decimal("0"),
        "max": Decimal("10"),
        "grades": {
            "A": Decimal("9"),
            "B": Decimal("7.5"),
            "C": Decimal("6"),
            "D": Decimal("4.5"),
            "F": Decimal("0"),
        },
        "display": lambda score: f"{score:.1f}/10",
    },
    "a-f": {
        "min": Decimal("0"),
        "max": Decimal("4"),
        "grades": {
            "A": Decimal("4"),
            "B": Decimal("3"),
            "C": Decimal("2"),
            "D": Decimal("1"),
            "F": Decimal("0"),
        },
        "display": lambda score: {0: "F", 1: "D", 2: "C", 3: "B", 4: "A"}.get(
            min(4, max(0, int(round(float(score))))),
            "F",
        ),
    },
    "gpa": {
        "min": Decimal("0"),
        "max": Decimal("4.0"),
        "grades": {
            "A": Decimal("4.0"),
            "B": Decimal("3.0"),
            "C": Decimal("2.0"),
            "D": Decimal("1.0"),
            "F": Decimal("0"),
        },
        "display": lambda score: f"{score:.2f}",
    },
    "uk-honours": {
        "min": Decimal("0"),
        "max": Decimal("100"),
        "grades": {
            "First": Decimal("70"),
            "2:1": Decimal("60"),
            "2:2": Decimal("50"),
            "Third": Decimal("40"),
            "Fail": Decimal("0"),
        },
        "display": lambda score: (
            "First"
            if float(score) >= 70
            else "2:1"
            if float(score) >= 60
            else "2:2"
            if float(score) >= 50
            else "Third"
            if float(score) >= 40
            else "Fail"
        ),
    },
    "ib-7": {
        "min": Decimal("0"),
        "max": Decimal("7"),
        "grades": {
            "7": Decimal("7"),
            "6": Decimal("6"),
            "5": Decimal("5"),
            "4": Decimal("4"),
            "3": Decimal("3"),
            "2": Decimal("2"),
            "1": Decimal("1"),
        },
        "display": lambda score: f"{float(score):.0f}/7",
    },
    "1-5": {
        "min": Decimal("0"),
        "max": Decimal("5"),
        "grades": {
            "A": Decimal("4.5"),
            "B": Decimal("4"),
            "C": Decimal("3.5"),
            "D": Decimal("3"),
            "F": Decimal("0"),
        },
        "display": lambda score: f"{float(score):.1f}/5",
    },
}


def convert_score(score, from_scale, to_scale):
    """
    Convert a score from one grading scale to another.

    Args:
        score: Numerical score (Decimal or float)
        from_scale: Source scale identifier ('0-20', '0-100', etc.)
        to_scale: Target scale identifier

    Returns:
        Decimal: Converted score rounded to 2 decimal places

    Examples:
        >>> convert_score(15, '0-20', '0-100')  # 75.0
        >>> convert_score(85, '0-100', '0-20')  # 17.0
        >>> convert_score(7.5, '0-10', 'gpa')   # 3.0
    """
    if from_scale == to_scale:
        return Decimal(str(score))

    cache_key = f"score_convert:{score}:{from_scale}:{to_scale}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from_config = GRADING_SCALES.get(from_scale)
    to_config = GRADING_SCALES.get(to_scale)

    if not from_config or not to_config:
        raise ValueError(f"Unknown scale: {from_scale} or {to_scale}")

    # Normalize to 0-1 range
    from_min = from_config["min"]
    from_max = from_config["max"]
    to_min = to_config["min"]
    to_max = to_config["max"]

    score_decimal = Decimal(str(score))

    # Handle edge case: score outside valid range
    score_decimal = max(from_min, min(from_max, score_decimal))

    # Normalize: (score - min) / (max - min)
    normalized = (score_decimal - from_min) / (from_max - from_min)

    # Convert: normalized * (to_max - to_min) + to_min
    converted = normalized * (to_max - to_min) + to_min

    result = converted.quantize(Decimal("0.01"))  # Round to 2 decimal places
    cache.set(cache_key, result, 3600)  # Cache for 1 hour

    return result


# Map AssessmentWeights.grading_scale (evals) to this module's scale id (RegionConfig / display).
# Use this for conversion and display when both systems are in use.
ASSESSMENT_WEIGHTS_SCALE_MAP = {
    "numeric_0_20": "0-20",
    "letter_a_e": "0-20",  # Letter grades A–E on 0–20 basis
    "gpa_4_0": "gpa",
    "percentage": "0-100",
    "numeric_1_5": "1-5",
}

# RegionConfig / migration profile aliases → GRADING_SCALES keys
REGION_SCALE_ALIASES = {
    **ASSESSMENT_WEIGHTS_SCALE_MAP,
    "numeric_0_100": "0-100",
    "numeric_0_10": "0-10",
    "letter_af": "a-f",
    "letter_a_f": "a-f",
    "gpa_4": "gpa",
    "th_0_4": "0-10",
    "uk_honours": "uk-honours",
    "uk-honors": "uk-honours",
    "uk_honors": "uk-honours",
    "ib_0_7": "ib-7",
    "ib-0-7": "ib-7",
    "ib": "ib-7",
}


def normalize_scale_id(scale: str | None, *, default: str = "0-100") -> str:
    """Map tenant / AssessmentWeights scale tokens to a GRADING_SCALES key."""
    if not scale:
        return default
    key = str(scale).strip()
    if key in GRADING_SCALES:
        return key
    return REGION_SCALE_ALIASES.get(key, default)


def scale_for_assessment_weights(weights) -> str:
    """
    Return the grading.py scale id for an AssessmentWeights instance (or None).
    Use for convert_score, get_grade_letter, format_score when weights are from AssessmentWeights.
    """
    if weights is None:
        return "0-20"
    scale = getattr(weights, "grading_scale", None)
    return ASSESSMENT_WEIGHTS_SCALE_MAP.get(scale, "0-20")


def get_scale_for_school(school) -> str:
    """
    Phase C: Return grading scale id for the school from tenant config (useLocalSettings / get_grading_schema_for_school).
    Use when grading or reporting in a tenant context so scale is not hardcoded.
    """
    if school is None:
        return "0-100"
    try:
        from apps.siteconfig.tenant_config import get_grading_schema_for_school

        raw = get_grading_schema_for_school(school).get("scale") or "0-100"
        return normalize_scale_id(raw, default="0-100")
    except (ImportError, AttributeError, TypeError, ValueError, KeyError):
        return "0-100"


def max_score_for_school(school) -> Decimal:
    """Upper bound for component scores on this school's active grading scale."""
    scale_id = get_scale_for_school(school)
    config = GRADING_SCALES.get(scale_id, GRADING_SCALES["0-100"])
    return config["max"]


def get_grade_letter(score, scale="0-20"):
    """
    Get letter grade (A-F) from numerical score.

    Args:
        score: Numerical score
        scale: Scale identifier

    Returns:
        str: Letter grade (A, B, C, D, or F)

    Examples:
        >>> get_grade_letter(18, '0-20')  # 'A'
        >>> get_grade_letter(12, '0-20')  # 'C'
        >>> get_grade_letter(90, '0-100')  # 'A'
    """
    config = GRADING_SCALES.get(scale, GRADING_SCALES["0-20"])
    grades = config["grades"]

    score_decimal = Decimal(str(score))

    for letter in ("A", "B", "C", "D", "F"):
        if score_decimal >= grades[letter]:
            return letter

    return "F"


def format_score(score, scale="0-20"):
    """
    Format score according to scale's display format.

    Args:
        score: Numerical score
        scale: Scale identifier

    Returns:
        str: Formatted score string

    Examples:
        >>> format_score(18.5, '0-20')  # '19/20'
        >>> format_score(87.3, '0-100')  # '87%'
        >>> format_score(3.75, 'gpa')  # '3.75'
    """
    config = GRADING_SCALES.get(scale, GRADING_SCALES["0-20"])
    display_fn = config["display"]

    try:
        return display_fn(float(score))
    except (TypeError, ValueError):
        return str(score)


def is_passing_score(score, scale="0-20"):
    """
    Determine if a score is passing (not an 'F').

    Args:
        score: Numerical score
        scale: Scale identifier

    Returns:
        bool: True if score is passing (grade != F)

    Examples:
        >>> is_passing_score(12, '0-20')  # True (grade C)
        >>> is_passing_score(8, '0-20')  # False (grade F)
    """
    letter_grade = get_grade_letter(score, scale)
    return letter_grade != "F"


def get_average_grade(scores, scale="0-20"):
    """
    Calculate average of multiple scores.

    Args:
        scores: List of numerical scores
        scale: Scale identifier

    Returns:
        Decimal: Average score rounded to 2 decimal places
    """
    if not scores:
        return Decimal("0")

    total = sum(Decimal(str(s)) for s in scores)
    average = total / Decimal(str(len(scores)))

    return average.quantize(Decimal("0.01"))


def score_to_normalized(score, school=None):
    """
    Convert a raw score to a normalized value in [0.0, 1.0] for cross-tenant/cross-system use (Rosetta Stone).
    Uses the school's grading scale from tenant config when school is provided.
    """
    scale_id = get_scale_for_school(school) if school else "0-20"
    config = GRADING_SCALES.get(scale_id, GRADING_SCALES["0-20"])
    mn = config["min"]
    mx = config["max"]
    score_decimal = Decimal(str(score))
    if mx == mn:
        return Decimal("0")
    normalized = (score_decimal - mn) / (mx - mn)
    normalized = max(Decimal("0"), min(Decimal("1"), normalized))
    return normalized.quantize(Decimal("0.0001"))


def scale_score(score, from_min, from_max, to_min=0, to_max=100):
    """
    Scale a score from one range to another (linear transformation).

    Args:
        score: Original score
        from_min: Minimum of original range
        from_max: Maximum of original range
        to_min: Minimum of target range (default 0)
        to_max: Maximum of target range (default 100)

    Returns:
        Decimal: Scaled score

    Examples:
        >>> scale_score(15, 0, 20, 0, 100)  # 75.0
        >>> scale_score(75, 0, 100, 0, 20)  # 15.0
    """
    score = Decimal(str(score))
    from_min = Decimal(str(from_min))
    from_max = Decimal(str(from_max))
    to_min = Decimal(str(to_min))
    to_max = Decimal(str(to_max))

    # Avoid division by zero
    if from_max == from_min:
        return to_min

    # Linear transformation: (score - from_min) / (from_max - from_min) * (to_max - to_min) + to_min
    normalized = (score - from_min) / (from_max - from_min)
    scaled = normalized * (to_max - to_min) + to_min

    return scaled.quantize(Decimal("0.01"))


# Currency: single source in siteconfig; re-export for backward compatibility
from apps.siteconfig.currency import CURRENCY_SYMBOLS, get_currency_symbol

__all__ = ["CURRENCY_SYMBOLS", "format_currency", "get_currency_symbol"]


def format_currency(amount, currency_code=None, include_symbol=True):
    """
    Format amount as currency (simple, no region separators).
    For region-aware display use template filter |format_currency or
    LocalizationService.format_currency(amount, region=region).

    Currency is local-first: an explicit ``currency_code`` wins, otherwise the
    platform default (never a hardcoded Cameroon XAF).
    """
    if not currency_code:
        from django.conf import settings

        currency_code = getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD")
    symbol = get_currency_symbol(currency_code)
    if include_symbol:
        return f"{symbol} {float(amount):,.2f}"
    return f"{float(amount):,.2f}"
