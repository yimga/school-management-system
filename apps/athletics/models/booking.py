"""Fixture venue booking with Postgres gist exclusion on overlapping intervals.

Clones the schoolops.ResourceBooking double-booking pattern verbatim: a
DateTimeRangeField + ExclusionConstraint keyed on (school, venue, time_range
overlap) is the race-proof backstop; the service layer (services/booking.py)
carries the SQLite pre-check for the non-Postgres test lane.
"""

from __future__ import annotations

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.fields.ranges import RangeOperators
from django.db import models
from django.db.models import F, Q


class FixtureVenueBooking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_venue_bookings",
    )
    venue = models.ForeignKey(
        "school_events.EventVenue",
        on_delete=models.CASCADE,
        related_name="athletics_bookings",
    )
    fixture = models.ForeignKey(
        "athletics.Fixture", on_delete=models.CASCADE, related_name="venue_bookings"
    )
    title = models.CharField(max_length=200)
    time_range = DateTimeRangeField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.CONFIRMED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "venue", "status"]),
        ]
        constraints = [
            ExclusionConstraint(
                name="exclude_overlapping_athletics_venue_bookings",
                expressions=[
                    (F("school_id"), RangeOperators.EQUAL),
                    (F("venue_id"), RangeOperators.EQUAL),
                    (F("time_range"), RangeOperators.OVERLAPS),
                ],
                condition=Q(status="confirmed"),
            ),
        ]

    def __str__(self) -> str:
        return f"booking venue={self.venue_id} {self.time_range}"


__all__ = ["FixtureVenueBooking"]
