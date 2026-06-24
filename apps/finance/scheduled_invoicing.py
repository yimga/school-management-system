"""
Timezone-aware scheduled fee-invoice generation (B1).

Each tenant can bill on their local calendar day-of-month at a configured local
hour. The hourly Celery beat calls :func:`is_invoice_generation_due_for_school`
before running the heavy invoice body.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_BILLING_HOUR = 6
DEFAULT_DAY_OF_MONTH = 1


def resolve_school_timezone(school: Any) -> ZoneInfo:
    tz_name = ""
    if school is not None:
        tz_name = str(getattr(school, "timezone", "") or "").strip()
    if not tz_name:
        from django.conf import settings

        tz_name = str(getattr(settings, "TIME_ZONE", "UTC") or "UTC")
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        logger.debug("invalid school timezone %r — falling back to UTC", tz_name)
        return ZoneInfo("UTC")


def school_local_now(school: Any, *, now_utc: datetime | None = None) -> datetime:
    if now_utc is None:
        from django.utils import timezone as dj_tz

        now_utc = dj_tz.now()
    if now_utc.tzinfo is None:
        from django.utils import timezone as dj_tz

        now_utc = dj_tz.make_aware(now_utc)
    return now_utc.astimezone(resolve_school_timezone(school))


def _effective_day_of_month(*, year: int, month: int, day_of_month: int) -> int:
    """Clamp billing day to the last day of short months (e.g. Feb 31 -> Feb 28)."""
    last = calendar.monthrange(year, month)[1]
    return min(max(1, day_of_month), last)


def is_local_billing_window(
    school: Any,
    schedule: dict[str, Any],
    *,
    now_utc: datetime | None = None,
) -> bool:
    """True when the school's local clock is on the configured billing day + hour."""
    mode = str(schedule.get("mode") or "academic_year_start").strip().lower()
    if mode != "monthly_day_of_month":
        return True

    local = school_local_now(school, now_utc=now_utc)
    target_day = int(schedule.get("day_of_month") or DEFAULT_DAY_OF_MONTH)
    target_hour = int(schedule.get("local_hour") or DEFAULT_LOCAL_BILLING_HOUR)
    effective_day = _effective_day_of_month(
        year=local.year, month=local.month, day_of_month=target_day
    )
    return local.day == effective_day and local.hour == target_hour


def is_invoice_generation_due(
    *,
    today: date,
    schedule: dict[str, Any],
    academic_year_start: date | None,
    term_start: date | None,
    dry_run: bool = False,
) -> bool:
    """Calendar schedule gate (academic / term / custom / monthly day-of-month)."""
    mode = str(schedule.get("mode") or "academic_year_start").strip().lower()

    if mode == "academic_year_start":
        if academic_year_start is None:
            return bool(dry_run)
        offset = int(schedule.get("academic_year_start_offset_days") or 0)
        return today >= academic_year_start + timedelta(days=offset)

    if mode == "term_start":
        if term_start is None:
            return bool(dry_run)
        offset = int(schedule.get("term_start_offset_days") or 0)
        return today >= term_start + timedelta(days=offset)

    if mode == "custom_date":
        custom_date_str = schedule.get("custom_date")
        if not custom_date_str:
            return bool(dry_run)
        try:
            target = date.fromisoformat(str(custom_date_str)[:10])
        except (TypeError, ValueError):
            return False
        return today >= target

    if mode == "monthly_day_of_month":
        target_day = int(schedule.get("day_of_month") or DEFAULT_DAY_OF_MONTH)
        effective = _effective_day_of_month(
            year=today.year, month=today.month, day_of_month=target_day
        )
        return today.day == effective

    return bool(dry_run)


def is_invoice_generation_due_for_school(
    school: Any,
    schedule: dict[str, Any],
    *,
    academic_year_start: date | None,
    term_start: date | None,
    dry_run: bool = False,
    now_utc: datetime | None = None,
) -> bool:
    """Combined timezone window + calendar due check."""
    local = school_local_now(school, now_utc=now_utc)
    mode = str(schedule.get("mode") or "academic_year_start").strip().lower()

    if mode == "monthly_day_of_month" and not dry_run:
        if not is_local_billing_window(school, schedule, now_utc=now_utc):
            return False

    return is_invoice_generation_due(
        today=local.date(),
        schedule=schedule,
        academic_year_start=academic_year_start,
        term_start=term_start,
        dry_run=dry_run,
    )


def billing_period_key(
    school: Any,
    schedule: dict[str, Any],
    *,
    academic_year_start: date | None = None,
    term_start: date | None = None,
    now_utc: datetime | None = None,
) -> str | None:
    """Stable idempotency key for a scheduled invoice generation window."""
    mode = str(schedule.get("mode") or "academic_year_start").strip().lower()
    if mode == "monthly_day_of_month":
        local = school_local_now(school, now_utc=now_utc)
        return local.strftime("%Y-%m")
    if mode == "academic_year_start" and academic_year_start is not None:
        return f"ay-{academic_year_start.isoformat()}"
    if mode == "term_start" and term_start is not None:
        return f"term-{term_start.isoformat()}"
    if mode == "custom_date":
        custom_date_str = schedule.get("custom_date")
        if custom_date_str:
            return f"custom-{str(custom_date_str)[:10]}"
    return None


def monthly_invoice_already_run(
    *,
    school: Any,
    billing_period: str,
    task_name: str = "finance.auto_generate_fee_invoices",
) -> bool:
    """True when this school already completed invoice generation for the period."""
    if not billing_period or school is None or getattr(school, "pk", None) is None:
        return False
    from apps.automation.models import AutomationExecutionLog

    return AutomationExecutionLog.objects.filter(
        task_name=task_name,
        school_id=school.pk,
        status__in=(
            AutomationExecutionLog.Status.SUCCESS,
            AutomationExecutionLog.Status.PARTIAL,
        ),
        execution_summary__billing_period=billing_period,
    ).exists()
