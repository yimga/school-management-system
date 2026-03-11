"""
Orchestration layer (Phase 10 — 4.1): long-running process support.
State, retries, compensation, SLA visibility. Operator workbench consumes these.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class ProcessDefinition(models.Model):
    """Definition of a long-running process type (admissions, re-enrollment, fee follow-up, etc.)."""
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # Optional: JSON schema for input/output, SLA targets, retry policy
    config_schema = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "orchestration"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name or self.code


class OrchestrationRun(models.Model):
    """A single run of a long-running process. Tracks state, retries, compensation."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        COMPENSATING = "compensating", "Compensating"
        CANCELLED = "cancelled", "Cancelled"

    definition = models.ForeignKey(
        ProcessDefinition,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="orchestration_runs",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    input_payload = models.JSONField(default=dict, blank=True)
    output_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    sla_deadline = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "orchestration"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["school", "definition", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.definition.code} #{self.pk} ({self.status})"

    @property
    def sla_overdue(self) -> bool:
        """True if SLA deadline has passed and run is still pending or running (Phase 10 — 4.1)."""
        from django.utils import timezone
        if not self.sla_deadline:
            return False
        if self.status not in (self.Status.PENDING, self.Status.RUNNING):
            return False
        return timezone.now() > self.sla_deadline
