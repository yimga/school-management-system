"""Behavior points ledger + restorative action tracking (metric 11)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class BehaviorPointLedger(models.Model):
    """Cumulative behavior points per student (tenant-scoped)."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="behavior_point_entries",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="behavior_point_entries",
    )
    incident = models.ForeignKey(
        "academics.Incident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="point_entries",
    )
    points = models.SmallIntegerField(
        help_text="Signed delta; negative = merit, positive = demerit.",
    )
    reason = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="behavior_points_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "academics"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "student", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} {self.points:+d}"


class RestorativeAction(models.Model):
    """Restorative follow-up tied to an incident."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="restorative_actions",
    )
    incident = models.ForeignKey(
        "academics.Incident",
        on_delete=models.CASCADE,
        related_name="restorative_actions",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restorative_actions_assigned",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "academics"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_status_display()})"
