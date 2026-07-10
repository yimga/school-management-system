"""Team roster memberships and fitness-to-play medical clearances."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.accounts.validators import FileSizeValidator, FileTypeValidator
from apps.athletics.constants import MEDICAL_CLEARANCE_MAX_UPLOAD_MB


def _clearance_upload_path(instance, filename: str) -> str:
    # A random per-file segment so a medical clearance (special-category child
    # health data) cannot be reached by guessing school_id + a common filename.
    school_id = getattr(instance, "school_id", "unknown")
    return f"athletics/medical/{school_id}/{uuid.uuid4().hex}/{filename}"


class TeamMembership(models.Model):
    """A student's place on a team roster."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending consent"
        ACTIVE = "active", "Active"
        INJURED = "injured", "Injured"
        SUSPENDED = "suspended", "Suspended"
        LEFT = "left", "Left"

    ROSTER_ACTIVE_STATUSES = ("pending", "active", "injured", "suspended")

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_memberships",
    )
    team = models.ForeignKey(
        "athletics.Team", on_delete=models.CASCADE, related_name="memberships"
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="athletics_memberships",
    )
    jersey_number = models.PositiveSmallIntegerField(null=True, blank=True)
    position = models.CharField(max_length=48, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    joined_at = models.DateField(null=True, blank=True)
    left_at = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["team", "jersey_number"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["team", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "student"],
                condition=Q(status__in=("pending", "active", "injured", "suspended")),
                name="uniq_active_membership_per_team",
            ),
            models.UniqueConstraint(
                fields=["team", "jersey_number"],
                condition=Q(status="active", jersey_number__isnull=False),
                name="uniq_active_jersey_per_team",
            ),
        ]

    def __str__(self) -> str:
        return f"member {self.student_id} team {self.team_id} ({self.status})"


class MedicalClearance(models.Model):
    """Fitness-to-play clearance for an athlete. GDPR-sensitive PII."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEARED = "cleared", "Cleared"
        EXPIRED = "expired", "Expired"
        REVOKED = "revoked", "Revoked"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_medical_clearances",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        db_constraint=False,
        related_name="athletics_medical_clearances",
    )
    sport = models.ForeignKey(
        "athletics.Sport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_clearances",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    cleared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="athletics_clearances_signed",
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    document = models.FileField(
        upload_to=_clearance_upload_path,
        null=True,
        blank=True,
        validators=[
            FileSizeValidator(max_size_mb=MEDICAL_CLEARANCE_MAX_UPLOAD_MB),
            FileTypeValidator(
                allowed_types=[
                    "application/pdf",
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                ],
                allowed_extensions=[".pdf", ".jpg", ".jpeg", ".png", ".webp"],
            ),
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["-valid_from"]
        indexes = [
            models.Index(fields=["school", "student", "status"]),
            models.Index(fields=["valid_until"]),
        ]

    def __str__(self) -> str:
        return f"clearance {self.student_id} ({self.status})"


__all__ = ["TeamMembership", "MedicalClearance"]
