"""Idempotent offline payroll / HR workflow captures (batch 1511)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class PayrollOfflineCaptureRecord(models.Model):
    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
        FAILED = "FAILED", "Failed"

    class Source(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        OFFLINE = "OFFLINE", "Offline"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="payroll_offline_captures",
    )
    workflow = models.CharField(max_length=64, db_index=True)
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.APPLIED,
        db_index=True,
    )
    source = models.CharField(
        max_length=12,
        choices=Source.choices,
        default=Source.OFFLINE,
    )
    fields_snapshot = models.JSONField(default=dict, blank=True)
    result_summary = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    payroll_run = models.ForeignKey(
        "payroll.PayrollRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offline_captures",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_offline_captures_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_payroll_offline_capture_client_id",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "workflow", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.workflow} ({self.status}) school={self.school_id}"
