"""
Dual-calendar display helpers (Gregorian primary + optional Hijri/Buddhist annotation).

Uses optional ``hijridate`` when installed; otherwise returns Gregorian-only (no fake conversion).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from apps.platform_runtime.localization import (
    CALENDAR_BUDDHIST,
    CALENDAR_GREGORIAN,
    CALENDAR_HIJRI,
    CALENDAR_HEBREW,
    calendar_type_for_school,
    format_school_date,
)


def _try_hijri_annotation(value: date) -> str | None:
    try:
        from hijridate import Gregorian

        g = Gregorian(value.year, value.month, value.day)
        h = g.to_hijri()
        return f"Hijri {h.day}/{h.month}/{h.year}"
    except ImportError:
        return None
    except (TypeError, ValueError, OverflowError):
        return None


def format_dual_calendar_date(
    value: date | datetime,
    *,
    school: Any = None,
    calendar_type: str | None = None,
    date_format: str | None = None,
) -> str:
    """
    Primary display uses tenant date_format; secondary annotation when calendar is non-Gregorian.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    csys = (calendar_type or calendar_type_for_school(school)).lower()
    primary = format_school_date(value, date_format=date_format)
    if csys in (CALENDAR_HIJRI, "islamic"):
        hijri = _try_hijri_annotation(value)
        if hijri:
            return f"{primary} ({hijri})"
    if csys == CALENDAR_BUDDHIST:
        # Buddhist era = Gregorian + 543 (Thailand); display-only, not liturgical calendar math.
        be_year = value.year + 543
        return f"{primary} (BE {be_year})"
    if csys == CALENDAR_HEBREW:
        hebrew = _try_hebrew_annotation(value)
        if hebrew:
            return f"{primary} ({hebrew})"
    return primary


def _try_hebrew_annotation(value: date) -> str | None:
    try:
        from pyluach import dates as hebrew_dates

        h = hebrew_dates.HebrewDate.from_pydate(value)
        return f"Hebrew {h.day}/{h.month}/{h.year}"
    except ImportError:
        return None
    except (TypeError, ValueError, OverflowError, AttributeError):
        return None
