"""
B3 (Master Blueprint): Pluralization, date/time, school week, calendars (Gregorian/Hijri).
Single module for tenant-aware locale and calendar behavior.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from django.utils import dateformat

# Calendar system codes (align with RegionConfig + registries)
CALENDAR_GREGORIAN = "gregorian"
CALENDAR_HIJRI = "hijri"
CALENDAR_BUDDHIST = "buddhist"
CALENDAR_HEBREW = "hebrew"

# RegionConfig.calendar_system values → canonical runtime codes
_CALENDAR_SYSTEM_ALIASES = {
    "gregorian": CALENDAR_GREGORIAN,
    "islamic": CALENDAR_HIJRI,
    "hijri": CALENDAR_HIJRI,
    "buddhist": CALENDAR_BUDDHIST,
    "hebrew": CALENDAR_HEBREW,
}


def plural_form(count: int, singular: str, plural: str | None = None) -> str:
    """
    Return singular or plural form based on count. For full i18n use gettext;
    this is the shared grammar for platform strings.
    """
    if count == 1:
        return singular
    return plural if plural else f"{singular}s"


def _date_format_to_django(pattern: str) -> str:
    """Map RegionConfig tokens (DD/MM/YYYY) to Django dateformat letters."""
    if not pattern or not isinstance(pattern, str):
        return "Y-m-d"
    return pattern.replace("YYYY", "Y").replace("DD", "d").replace("MM", "m")


def format_school_date(
    value: date | datetime,
    *,
    locale_code: str = "en",
    date_format: str | None = None,
) -> str:
    """
    Format a date for display using school/region preferences. Falls back to ISO date.
    """
    del locale_code  # reserved for future Babel/gettext locale formatting
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if date_format:
        try:
            return dateformat.format(value, _date_format_to_django(date_format))
        except (TypeError, ValueError, AttributeError):
            return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d")


def school_week_for_date(
    d: date,
    *,
    academic_year_start: date | None = None,
    week_start_day: int = 0,
) -> int:
    """
    Return 1-based school week number for the given date.

    week_start_day: 0=Monday … 6=Sunday (matches datetime.date.weekday()).
    academic_year_start: first day of the academic year; week 1 begins on the
    week_start_day-aligned boundary on or before that date.
    """
    start = academic_year_start or date(d.year, 1, 1)
    if d < start:
        start = date(d.year - 1, 1, 1)
    week_start_day = int(week_start_day) % 7
    days_back = (start.weekday() - week_start_day) % 7
    anchor = start - timedelta(days=days_back)
    if d < anchor:
        anchor = date(anchor.year - 1, anchor.month, anchor.day)
        days_back = (anchor.weekday() - week_start_day) % 7
        anchor = anchor - timedelta(days=days_back)
    delta = (d - anchor).days
    return max(1, (delta // 7) + 1)


def calendar_type_for_school(school: Any) -> str:
    """
    Return calendar system code for the school (e.g. gregorian, hijri).
    Resolves from school.default_region / RegionConfig.calendar_system.
    """
    if school is None:
        return CALENDAR_GREGORIAN
    try:
        region = getattr(school, "default_region", None)
        raw = None
        if region:
            raw = getattr(region, "calendar_system", None) or getattr(
                region, "calendar_system_code", None
            )
        if raw:
            key = str(raw).strip().lower()
            return _CALENDAR_SYSTEM_ALIASES.get(key, key)
    except (AttributeError, TypeError, ValueError):
        pass
    return CALENDAR_GREGORIAN


def week_start_day_for_school(school: Any) -> int:
    """0=Monday … 6=Sunday from tenant locale (RegionConfig or school.settings)."""
    if school is None:
        return 0
    try:
        from apps.siteconfig.tenant_config import get_tenant_locale

        return int(get_tenant_locale(school=school).get("week_start_day", 0)) % 7
    except (ImportError, AttributeError, TypeError, ValueError):
        return 0


def calendar_week_bounds(
    d: date,
    *,
    week_start_day: int = 0,
) -> tuple[date, date]:
    """Inclusive (start, end) for the calendar week containing ``d``."""
    week_start_day = int(week_start_day) % 7
    days_back = (d.weekday() - week_start_day) % 7
    start = d - timedelta(days=days_back)
    return start, start + timedelta(days=6)
