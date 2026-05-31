"""TenantReactivationAttempt — log + suppression for the 4-cadence
win-back campaign (v4.00.98 Phase 4).

Each row records that we tried to email a particular school's admin at a
particular cadence stage (30 / 60 / 90 / 120 days of inactivity). The
scanner uses this table both to PICK eligible schools AND to AVOID
re-sending the same cadence twice in the same window.
"""

from __future__ import annotations

from django.db import models


class TenantReactivationCadence(models.TextChoices):
    """Cadence stages for the win-back ladder."""

    DAY_30 = "30d", "30 days inactive"
    DAY_60 = "60d", "60 days inactive"
    DAY_90 = "90d", "90 days inactive"
    DAY_120 = "120d", "120 days inactive (final)"


class TenantReactivationAttempt(models.Model):
    """One emailed reactivation attempt at a specific cadence stage."""

    school_id = models.CharField(max_length=40, db_index=True)
    school_name = models.CharField(max_length=160, blank=True, default="")
    recipient_email = models.CharField(max_length=254, blank=True, default="")
    recipient_email_hash = models.CharField(max_length=16, blank=True, default="")

    cadence = models.CharField(
        max_length=8,
        choices=TenantReactivationCadence.choices,
        db_index=True,
    )

    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    delivery_event_id = models.CharField(max_length=64, blank=True, default="")
    delivery_ok = models.BooleanField(default=True)
    delivery_error_kind = models.CharField(max_length=64, blank=True, default="")

    # Engagement tracking (optional — set if a webhook reports back later)
    opened_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    converted_back_at = models.DateTimeField(null=True, blank=True)

    suppressed = models.BooleanField(default=False)
    suppressed_reason = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Tenant reactivation attempt"
        verbose_name_plural = "Tenant reactivation attempts"
        ordering = ["-sent_at"]
        indexes = [
            models.Index(fields=["school_id", "cadence", "-sent_at"], name="treact_school_cadence_idx"),
            models.Index(fields=["cadence", "-sent_at"], name="treact_cadence_sent_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school_id", "cadence"],
                condition=models.Q(suppressed=False),
                name="treact_unique_school_cadence_not_suppressed",
            ),
        ]

    def __str__(self) -> str:
        return f"react[{self.cadence}] school={self.school_id}"
