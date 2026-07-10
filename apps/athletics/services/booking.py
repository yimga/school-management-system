"""Fixture venue booking with Postgres exclusion for single-occupancy venues.

Copies the ``apps.schoolops.booking_services`` pattern: a Postgres time_range
overlap pre-check on the fast path, an interval-overlap scan of confirmed
bookings on the SQLite test lane, and the model's ``ExclusionConstraint`` as the
race-proof backstop (an ``IntegrityError`` is mapped to ``BookingConflictError``).
A venue holds at most one confirmed fixture booking per instant.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class BookingConflictError(Exception):
    """Raised when a fixture venue booking overlaps an existing reservation."""


def _aware(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def overlapping_confirmed_count(*, school, venue, start: datetime, end: datetime) -> int:
    from apps.athletics.models import FixtureVenueBooking

    start = _aware(start)
    end = _aware(end)
    qs = FixtureVenueBooking.objects.filter(
        school_id=getattr(school, "id", school),
        venue=venue,
        status=FixtureVenueBooking.Status.CONFIRMED,
    )
    if connection.vendor == "postgresql":
        return qs.filter(time_range__overlap=(start, end)).count()
    overlap = 0
    for row in qs.iterator():
        lower = row.time_range.lower
        upper = row.time_range.upper
        if lower is None or upper is None:
            continue
        lower = _aware(lower)
        upper = _aware(upper)
        if start < upper and end > lower:
            overlap += 1
    return overlap


@transaction.atomic
def book_fixture_venue(
    *,
    school: Any,
    venue: Any,
    fixture: Any,
    title: str,
    start: datetime,
    end: datetime,
) -> Any:
    """Create a confirmed venue booking; raises BookingConflictError on overlap."""
    from apps.athletics.models import FixtureVenueBooking

    if end <= start:
        raise ValueError("end must be after start")
    if getattr(venue, "school_id", None) not in (None, getattr(school, "id", school)):
        raise ValueError("venue school mismatch")

    overlap = overlapping_confirmed_count(
        school=school, venue=venue, start=start, end=end
    )
    if overlap >= 1:
        raise BookingConflictError(
            str(_("This venue is already booked for that time."))
        )

    try:
        return FixtureVenueBooking.objects.create(
            school=school,
            venue=venue,
            fixture=fixture,
            title=(title or "").strip()[:200] or str(_("Fixture")),  # magic-number-allow: title-charfield-max-length-fit
            time_range=(_aware(start), _aware(end)),
            status=FixtureVenueBooking.Status.CONFIRMED,
        )
    except IntegrityError as exc:
        raise BookingConflictError(
            str(_("This venue is already booked for that time."))
        ) from exc


def cancel_fixture_venue_booking(*, booking: Any) -> None:
    from apps.athletics.models import FixtureVenueBooking

    if booking.status == FixtureVenueBooking.Status.CANCELLED:
        return
    booking.status = FixtureVenueBooking.Status.CANCELLED
    booking.save(update_fields=["status", "updated_at"])


__all__ = [
    "BookingConflictError",
    "book_fixture_venue",
    "cancel_fixture_venue_booking",
    "overlapping_confirmed_count",
]
