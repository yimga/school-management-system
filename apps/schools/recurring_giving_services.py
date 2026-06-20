"""
Recurring (scheduled) giving (Wedge 5).

The platform has NO card-on-file auto-charge capability, so a recurring schedule
MINTS a ``DonationPledge`` on each due date — an expected gift the donor fulfils as
usual — rather than charging a card. A daily periodic job calls
``mint_due_recurring_pledges()``; each schedule advances its own ``next_run_date``.
Imports are lazy to avoid app-load cycles.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta
from typing import Any

from django.db import DatabaseError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _add_months(d: date, months: int) -> date:
    """Step a date by whole months, clamping the day to the target month's length."""
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _advance(d: date, frequency: str) -> date:
    if frequency == "weekly":
        return d + timedelta(days=7)
    if frequency == "quarterly":
        return _add_months(d, 3)
    if frequency == "annual":
        return _add_months(d, 12)
    # monthly (default)
    return _add_months(d, 1)


def mint_pledge_for_schedule(schedule, *, on_date=None) -> dict[str, Any]:
    """Mint one DonationPledge for a schedule's current cycle and advance next_run_date."""
    from apps.schools.models import DonationPledge, RecurringDonationSchedule

    if schedule.status != RecurringDonationSchedule.Status.ACTIVE:
        return {"ok": False, "error": "Schedule is not active."}
    on_date = on_date or timezone.now().date()
    with transaction.atomic():
        pledge = DonationPledge.objects.create(
            school_id=schedule.school_id,
            donor_id=schedule.donor_id,
            campaign_id=schedule.campaign_id,
            amount=schedule.amount,
            currency=schedule.currency,
            due_date=schedule.next_run_date,
        )
        schedule.pledges_created += 1
        schedule.last_run_at = timezone.now()
        schedule.next_run_date = _advance(schedule.next_run_date, schedule.frequency)
        fields = ["pledges_created", "last_run_at", "next_run_date", "updated_at"]
        if schedule.end_date and schedule.next_run_date > schedule.end_date:
            schedule.status = RecurringDonationSchedule.Status.COMPLETED
            fields.append("status")
        schedule.save(update_fields=fields)
    return {"ok": True, "pledge_id": pledge.pk, "next_run_date": schedule.next_run_date}


def mint_due_recurring_pledges(*, today=None, limit: int = 500) -> dict[str, Any]:
    """
    Mint pledges for every ACTIVE schedule whose ``next_run_date`` is due. This is the
    periodic-job entry point; failure of one schedule never aborts the batch.
    """
    from apps.schools.models import RecurringDonationSchedule

    today = today or timezone.now().date()
    due = RecurringDonationSchedule.objects.filter(
        status=RecurringDonationSchedule.Status.ACTIVE,
        next_run_date__lte=today,
    ).order_by("next_run_date")[:limit]
    minted = 0
    for schedule in due:
        try:
            result = mint_pledge_for_schedule(schedule, on_date=today)
            if result.get("ok"):
                minted += 1
        except (DatabaseError, ValueError, TypeError) as e:
            logger.warning(
                "recurring pledge mint failed for schedule=%s: %s", schedule.pk, e
            )
    return {"ok": True, "minted": minted}
