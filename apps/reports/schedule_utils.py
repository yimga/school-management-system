"""Shared next-run computation for ``TenantReportSchedule`` (API + management command)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

logger = logging.getLogger(__name__)


def resolve_schedule_timezone(school=None):
    """The TENANT's zone for a scheduled report -- never the server's guess.

    ``TenantReportSchedule.schedule_time`` is a wall-clock time the school typed
    ("send the digest at 07:00"), so it only means what they meant when it is
    combined in THEIR zone. Combining it in the platform zone (``TIME_ZONE``,
    ``UTC`` on the deployed cloud) fires a Douala school's 07:00 report at 08:00
    local and a Mumbai school's at 12:30 -- the schedule silently means a
    different hour for every tenant outside the server's zone. Mirrors
    ``apps.sync_engine.schedule_policy.school_timezone``.

    An unknown or blank zone degrades to the active Django timezone rather than
    raising: a bad zone string must never stop a schedule advancing.
    """
    name = (getattr(school, "timezone", "") or "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            logger.warning(
                "report schedule: unknown timezone %r; using the platform default",
                name,
            )
    return timezone.get_current_timezone()


def compute_next_scheduled_run(
    last_run, frequency: str, schedule_time: time, school=None
):
    """
    Compute ``next_run`` from ``last_run`` + ``frequency`` and wall-clock ``schedule_time``.

    When ``last_run`` is None (new schedule), uses current time as the base so the first
    run lands in the future according to frequency.

    ``school`` supplies the zone the wall-clock ``schedule_time`` is expressed in.
    It is optional so existing call sites keep working, but passing it is what
    makes 07:00 mean 07:00 *at the school*.
    """
    if last_run is None:
        base = timezone.now()
    else:
        base = last_run
    tz = resolve_schedule_timezone(school)
    # The calendar day must be the TENANT's day too: at 23:00 UTC a school in
    # Asia/Kolkata is already on tomorrow, and anchoring to the server's date
    # would schedule a run that has, locally, already gone by.
    base_date = timezone.localtime(base, tz).date() if timezone.is_aware(base) else base.date()
    next_naive = datetime.combine(base_date, schedule_time, tzinfo=tz)
    if next_naive <= base:
        next_naive = next_naive + timedelta(days=1)
    if frequency == "DAILY":
        next_run = next_naive
    elif frequency == "WEEKLY":
        next_run = next_naive + timedelta(days=7)
    elif frequency == "MONTHLY":
        if next_naive.month == 12:
            next_run = next_naive.replace(year=next_naive.year + 1, month=1)
        else:
            next_run = next_naive.replace(month=next_naive.month + 1)
    elif frequency == "QUARTERLY":
        next_run = next_naive + timedelta(days=90)
    else:
        next_run = next_naive + timedelta(days=1)
    return next_run
