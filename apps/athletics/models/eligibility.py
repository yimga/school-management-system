"""Materialized athlete-eligibility snapshots written by the resolver."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class EligibilityRecord(models.Model):
    """A recompute-and-cache snapshot of a membership's eligibility to play."""

    class Status(models.TextChoices):
        ELIGIBLE = "eligible", "Eligible"
        INELIGIBLE = "ineligible", "Ineligible"
        PROVISIONAL = "provisional", "Provisional"
        PENDING = "pending", "Pending"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_eligibility_records",
    )
    membership = models.ForeignKey(
        "athletics.TeamMembership",
        on_delete=models.CASCADE,
        related_name="eligibility_records",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    academic_ok = models.BooleanField(default=False)
    attendance_ok = models.BooleanField(default=False)
    medical_ok = models.BooleanField(default=False)
    consent_ok = models.BooleanField(default=False)
    reason = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="athletics_eligibility_checks",
    )

    class Meta:
        app_label = "athletics"
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["membership", "checked_at"]),
        ]

    def __str__(self) -> str:
        return f"eligibility {self.membership_id} ({self.status})"


__all__ = ["EligibilityRecord"]
