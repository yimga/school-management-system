"""Runtime calendar + local clock for dashboard calendar/weather sections.

Local-first: school/tenant timezone from SiteSettings feature flags.
Global-second: UTC reference line when local zone is not UTC.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _resolve_timezone(request: Any) -> str:
    site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    flags = getattr(site, "backend_feature_flags", None) or {}
    tz = str(
        flags.get("header_weather_timezone")
        or getattr(settings, "TIME_ZONE", None)
        or "UTC"
    ).strip()
    if not tz:
        return "UTC"
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return "UTC"


def _format_local_time(dt, *, with_seconds: bool = True) -> str:
    locale = getattr(settings, "LANGUAGE_CODE", "en") or "en"
    if with_seconds:
        pattern = {"hour": "numeric", "minute": "2-digit", "second": "2-digit"}
    else:
        pattern = {"hour": "numeric", "minute": "2-digit"}
    try:
        from django.utils.formats import date_format

        return date_format(dt, format="TIME_FORMAT")
    except Exception:
        pass
    try:
        from babel.dates import format_time

        return format_time(dt, format="medium", locale=locale)
    except Exception:
        return dt.strftime("%I:%M:%S %p" if with_seconds else "%I:%M %p").lstrip("0")


def resolve_calendar_weather_runtime(request: Any) -> dict[str, Any]:
    """Build a 7-day strip anchored on the resolved local timezone."""
    tz_name = _resolve_timezone(request)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"

    local_now = timezone.now().astimezone(tz)
    utc_now = timezone.now().astimezone(ZoneInfo("UTC"))

    days: list[dict[str, Any]] = []
    for offset in range(7):
        day = local_now.date() + timedelta(days=offset)
        days.append({
            "day_short": day.strftime("%a"),
            "day_num": day.strftime("%d"),
            "is_today": offset == 0,
            "weather_icon": "",
            "temp_display": "",
            "event_label": "",
        })

    global_suffix = ""
    if tz_name.upper() != "UTC":
        global_suffix = utc_now.strftime("%H:%M UTC")

    return {
        "enabled": True,
        "title": _("Week ahead"),
        "local_timezone": tz_name,
        "now_date_display": local_now.strftime("%A, %b %d"),
        "now_time_display": _format_local_time(local_now),
        "global_time_display": global_suffix,
        "days": days,
    }


__all__ = ["resolve_calendar_weather_runtime"]
