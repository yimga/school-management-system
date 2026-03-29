"""Shared next-run computation for ``TenantReportSchedule`` (API + management command)."""

from __future__ import annotations

from datetime import datetime, timedelta, time

from django.utils import timezone


def compute_next_scheduled_run(last_run, frequency: str, schedule_time: time):
    """
    Compute ``next_run`` from ``last_run`` + ``frequency`` and wall-clock ``schedule_time``.

    When ``last_run`` is None (new schedule), uses current time as the base so the first
    run lands in the future according to frequency.
    """
    if last_run is None:
        base = timezone.now()
    else:
        base = last_run
    base_date = base.date()
    tz = timezone.get_current_timezone()
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
