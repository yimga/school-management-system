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
def create_resource_booking(
    *,
    school: Any,
    resource: Any,
    booked_by: Any,
    title: str,
    start: datetime,
    end: datetime,
) -> Any:
    """Create a confirmed booking; raises BookingConflictError on overlap."""
    from apps.schoolops.models_resource_booking import ResourceBooking

    if end <= start:
        raise ValueError("end must be after start")
    if resource.school_id != school.id:
        raise ValueError("resource school mismatch")

    capacity = max(1, int(getattr(resource, "capacity", 1) or 1))
    overlap = overlapping_confirmed_count(resource=resource, start=start, end=end)
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
