"""Room / asset booking with Postgres exclusion for capacity=1 resources."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class BookingConflictError(Exception):
    """Raised when a booking overlaps an existing reservation."""


def _aware(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _range_bounds(value):
    """Return ``(lower, upper)`` datetimes for a stored ``time_range``, backend-safe.

    Postgres reads a ``DateTimeRangeField`` back as a Range object with datetime
    ``.lower`` / ``.upper``. SQLite has no ``from_db_value`` for the field, so the
    column round-trips as its canonical text ``'[lower,upper)'`` — a plain ``str``
    whose ``.lower`` is the string method, NOT a bound — so parse the literal
    there. Mirrors ``apps.academics.scheduling._parse_range_text``.
    """
    if value is None:
        return (None, None)
    if isinstance(value, str):
        s = value.strip()
        if not s or "empty" in s.lower():
            return (None, None)
        if s[0] in "[(" and s[-1] in ")]":
            s = s[1:-1]
        if "," not in s:
            return (None, None)
        lo_str, hi_str = s.split(",", 1)

        def _parse(raw: str):
            raw = raw.strip().strip('"')
            if not raw:
                return None
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                return None

        return (_parse(lo_str), _parse(hi_str))
    return (getattr(value, "lower", None), getattr(value, "upper", None))


def overlapping_confirmed_count(*, resource, start: datetime, end: datetime) -> int:
    from apps.schoolops.models_resource_booking import ResourceBooking

    start = _aware(start)
    end = _aware(end)
    qs = ResourceBooking.objects.filter(
        school_id=resource.school_id,
        resource=resource,
        status=ResourceBooking.Status.CONFIRMED,
    )
    if connection.vendor == "postgresql":
        return qs.filter(time_range__overlap=(start, end)).count()
    overlap = 0
    for row in qs.iterator():
        lower, upper = _range_bounds(row.time_range)
        if lower is None or upper is None:
            continue
        lower = _aware(lower)
        upper = _aware(upper)
        if start < upper and end > lower:
            overlap += 1
    return overlap


@transaction.atomic
def create_resource_booking(
    *,
    school: Any,
    resource: Any,
    booked_by: Any,
    title: str,
    start: datetime,
    end: datetime,
) -> Any:
    """Create a confirmed booking; raises BookingConflictError on overlap.

    Concurrency: a resource with ``capacity > 1`` cannot be protected by the
    Postgres exclusion constraint (it only expresses "no two overlap", i.e.
    capacity=1), so capacity is enforced here by a count. A naive
    ``count() < capacity`` then ``create()`` has a check-then-act (TOCTOU) race —
    two simultaneous requests both read ``count == capacity-1`` and both insert,
    exceeding capacity. We close the race by taking a ``SELECT ... FOR UPDATE``
    row lock on the ``BookableResource`` row for the life of this atomic block:
    concurrent bookings for the SAME resource serialize on that lock, so the
    second request blocks until the first commits and then re-counts against the
    now-current state. The lock is a harmless no-op on backends without row
    locking (e.g. SQLite in tests), which already serialize writers globally.
    """
    from apps.schoolops.models_resource_booking import (
        BookableResource,
        ResourceBooking,
    )

    if end <= start:
        raise ValueError("end must be after start")
    if resource.school_id != school.id:
        raise ValueError("resource school mismatch")

    # Serialize concurrent bookings for this resource (see docstring). Read the
    # live capacity from the locked row so a just-committed capacity change is
    # respected. Fall back to the passed-in object if the row vanished.
    locked = (
        BookableResource.objects.select_for_update().filter(pk=resource.pk).first()
        or resource
    )
    capacity = max(1, int(getattr(locked, "capacity", 1) or 1))
    overlap = overlapping_confirmed_count(resource=locked, start=start, end=end)
    if overlap >= capacity:
        raise BookingConflictError(
            str(_("This resource is already booked for that time."))
        )

    try:
        return ResourceBooking.objects.create(
            school=school,
            resource=resource,
            booked_by=booked_by,
            title=(title or "").strip()[:200] or str(_("Booking")),
            time_range=(_aware(start), _aware(end)),
            status=ResourceBooking.Status.CONFIRMED,
            # capacity=1 → exclusive → indexed by the partial DB constraint as a
            # belt-and-suspenders backstop; capacity>1 → excluded from the index,
            # capacity is enforced by the locked count above.
            enforce_exclusive=(capacity == 1),
        )
    except IntegrityError as exc:
        raise BookingConflictError(
            str(_("This resource is already booked for that time."))
        ) from exc


def cancel_resource_booking(*, booking: Any) -> None:
    from apps.schoolops.models_resource_booking import ResourceBooking

    if booking.status == ResourceBooking.Status.CANCELLED:
        return
    booking.status = ResourceBooking.Status.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
