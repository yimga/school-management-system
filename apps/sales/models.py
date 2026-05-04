from __future__ import annotations

from django.conf import settings
from django.db import models


class PipelineStage(models.Model):
    """
    Normalized stage row (seeded). Keeps display labels stable if keys are referenced in code.
    """

    key = models.SlugField(max_length=32, unique=True, db_index=True)
    label = models.CharField(max_length=64)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "pk")

    def __str__(self) -> str:
        return self.label


class Lead(models.Model):
    """Prospect or customer record for founder-led GTM (not billing)."""

    school_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    stage = models.ForeignKey(
        PipelineStage,
        on_delete=models.PROTECT,
        related_name="leads",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional one-line summary; use Activity for dated entries.",
    )
    decision_maker = models.CharField(
        max_length=200,
        blank=True,
        help_text="Primary decision-maker name or title (internal).",
    )
    deal_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_sales_leads",
        help_text="Internal owner for follow-up (platform operator).",
    )
    next_follow_up = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_sales_leads",
    )

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return self.school_name


class ActivityLog(models.Model):
    """Dated note on a lead (internal only)."""

    lead = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="activity_logs"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_lead_activities",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.lead_id} @ {self.created_at}"
