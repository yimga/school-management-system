"""
Tenant-overridable attendance and fee-type registries (SOT §0.2.2, Tier 1c).
"""

from __future__ import annotations

from django.db import models


class TenantAttendanceCode(models.Model):
    """Per-school attendance codes (P/A/T/L excused, etc.). Merged with defaults in get_effective_attendance_codes."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="tenant_attendance_codes",
    )
    code = models.CharField(max_length=16, db_index=True)
    label = models.CharField(max_length=160)
    counts_as_present = models.BooleanField(default=False)
    is_excused_absence = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]
        unique_together = [("school", "code")]
        verbose_name = "Tenant attendance code"
        verbose_name_plural = "Tenant attendance codes"

    def __str__(self):
        return f"{self.school_id}:{self.code}"


class TenantFeeTypeEntry(models.Model):
    """Per-school fee line types; optional link to global FeeCategoryRegistry."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="tenant_fee_type_entries",
    )
    code = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=200)
    fee_category = models.ForeignKey(
        "registries.FeeCategoryRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant_fee_entries",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]
        unique_together = [("school", "code")]
        verbose_name = "Tenant fee type entry"
        verbose_name_plural = "Tenant fee type entries"

    def __str__(self):
        return f"{self.school_id}:{self.code}"
