"""
B3 (Master Blueprint): Pluralization, date/time, school week, calendars (Gregorian/Hijri).
Single module for tenant-aware locale and calendar behavior.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Calendar system codes (align with registries)
CALENDAR_GREGORIAN = "gregorian"
CALENDAR_HIJRI = "hijri"


def plural_form(count: int, singular: str, plural: str | None = None) -> str:
    """
    Return singular or plural form based on count. For full i18n use gettext;
    this is the shared grammar for platform strings.
    """
    if count == 1:
        return singular
    return plural if plural else f"{singular}s"


def format_school_date(
    value: date | datetime,
    *,
    locale_code: str = "en",
    date_format: str | None = None,
) -> str:
    """
    Format a date for display using school/region preferences. Falls back to ISO date.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if date_format:
        return value.strftime(
            date_format.replace("%Y", "%Y").replace("%m", "%m").replace("%d", "%d")
        )
    return value.strftime("%Y-%m-%d")


def school_week_for_date(
    d: date,
    *,
    academic_year_start: date | None = None,
    week_start_day: int = 0,
) -> int:
    """
    Return 1-based school week number for the given date. week_start_day: 0=Monday, 6=Sunday.
    academic_year_start: when not provided, use calendar year start.
    """
    start = academic_year_start or date(d.year, 1, 1)
    if d < start:
        start = date(d.year - 1, 1, 1)
    delta = (d - start).days
    return max(1, (delta // 7) + 1)


def calendar_type_for_school(school: Any) -> str:
    """
    Return calendar system code for the school (e.g. gregorian, hijri).
    Resolves from school.default_region / RegionConfig or policy; defaults to gregorian.
    """
    if school is None:
        return CALENDAR_GREGORIAN
    try:
        region = getattr(school, "default_region_id", None) and getattr(
            school, "default_region", None
        )
        if region and getattr(region, "calendar_system_code", None):
            return (region.calendar_system_code or CALENDAR_GREGORIAN).lower()
    except (AttributeError, TypeError, ValueError):
        pass
    return CALENDAR_GREGORIAN
