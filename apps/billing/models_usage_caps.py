"""v4.00.36 Phase 3 — UsageCap model.

Lives in its own module so the helper code in ``apps.billing.usage_caps``
can re-export without circular imports. Imported by ``apps.billing.models``
so Django's app-loading machinery picks the model up.
"""

from __future__ import annotations

from django.db import models


class UsageCap(models.Model):
    """Per-tenant cap declaration for a single usage dimension."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="usage_caps",
    )
    dimension = models.CharField(
        max_length=64,
        help_text="Must be one of apps.billing.models_metering.USAGE_DIMENSION_CODES.",
    )
    soft_warn_at = models.PositiveBigIntegerField(
        default=0,
        help_text="Emit a soft warning at or above this quantity. 0 = no soft warn.",
    )
    hard_cap = models.PositiveBigIntegerField(
        default=0,
        help_text="At or above this quantity, BillingAccount auto-suspends. 0 = no hard cap.",
    )
    period_grain = models.CharField(
        max_length=16,
        default="day",
        choices=[("day", "Daily window"), ("month", "Calendar month")],
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "billing"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "dimension"],
                name="billing_uniq_usage_cap_school_dimension",
            )
        ]
        ordering = ["school", "dimension"]
        verbose_name = "Usage cap"
        verbose_name_plural = "Usage caps"

    def __str__(self) -> str:
        return f"{self.school_id}/{self.dimension}: soft={self.soft_warn_at} hard={self.hard_cap}"


__all__ = ["UsageCap"]
