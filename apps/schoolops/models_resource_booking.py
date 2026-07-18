"""Bookable rooms/assets with Postgres gist exclusion on overlapping intervals."""

from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.fields.ranges import RangeOperators
from django.db import models
from django.db.models import F, Q


class BookableResource(models.Model):
    class ResourceType(models.TextChoices):
        ROOM = "room", "Room"
        LAB = "lab", "Lab"
        HALL = "hall", "Hall"
        ASSET = "asset", "Asset"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="bookable_resources",
    )
    name = models.CharField(max_length=120)
    resource_type = models.CharField(
        max_length=16,
        choices=ResourceType.choices,
        default=ResourceType.ROOM,
    )
    capacity = models.PositiveSmallIntegerField(
        default=1,
        help_text="Concurrent bookings allowed; capacity=1 uses DB exclusion.",
    )
    hostel_room = models.ForeignKey(
        "schoolops.HostelRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookable_resources",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        ordering = ["name"]
        unique_together = [("school", "name")]
        indexes = [
            models.Index(fields=["school", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.school_id})"


class ResourceBooking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="resource_bookings",
    )
    resource = models.ForeignKey(
        BookableResource,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resource_bookings_created",
    )
    title = models.CharField(max_length=200)
    time_range = DateTimeRangeField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    enforce_exclusive = models.BooleanField(
        default=True,
        db_default=True,
        help_text=(
            "True when this booking must not overlap any other exclusive booking "
            "on the same resource — the capacity=1 case, enforced by the partial "
            "DB exclusion constraint below. Multi-capacity (capacity>1) bookings "
            "are False: they are excluded from the DB overlap index and enforced "
            "in the service layer under a resource row lock. Defaults True so any "
            "row inserted outside the service layer is treated as exclusive — "
            "failing safe against silent double-booking."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "resource", "status"]),
        ]
        constraints = [
            # Partial exclusion: only EXCLUSIVE (capacity=1) confirmed bookings are
            # indexed, so no two overlap for the same (school, resource). Postgres
            # cannot express "at most N overlapping" for N>1, so multi-capacity
            # rows (enforce_exclusive=False) are deliberately excluded here and
            # enforced concurrency-safely in booking_services.create_resource_booking
            # under a select_for_update lock on the resource row.
            ExclusionConstraint(
                name="exclude_overlapping_resource_bookings",
                expressions=[
                    (F("school_id"), RangeOperators.EQUAL),
                    (F("resource_id"), RangeOperators.EQUAL),
                    (F("time_range"), RangeOperators.OVERLAPS),
                ],
                condition=Q(status="confirmed", enforce_exclusive=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.resource.name} {self.time_range}"
