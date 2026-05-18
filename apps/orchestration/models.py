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
    # Move 2: monotonically-incrementing version number for this definition.
    # Each time the definition is "published", a ProcessDefinitionVersion row is created
    # with this number, and current_version is bumped. Runs bind to a specific
    # ProcessDefinitionVersion so re-deploys never break in-flight work.
    current_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "orchestration"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name or self.code


class ProcessDefinitionVersion(models.Model):
    """Frozen snapshot of a ProcessDefinition at publish time.

    Move 2 of the strategic moves: workflows must be versioned so that
    a re-deploy or schema change never breaks already-running instances.
    """

    definition = models.ForeignKey(
        ProcessDefinition,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField()
    config_snapshot = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    is_current = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(auto_now_add=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        app_label = "orchestration"
        unique_together = [["definition", "version_number"]]
        ordering = ["definition", "-version_number"]
        indexes = [
            models.Index(fields=["definition", "is_current"], name="orch_pdv_def_cur_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.definition.code}@v{self.version_number}"


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
    definition_version = models.ForeignKey(
        ProcessDefinitionVersion,
        on_delete=models.PROTECT,
        related_name="runs",
        null=True,
        blank=True,
        help_text="Move 2: the exact version snapshot this run is bound to.",
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


class OrchestrationStepEvent(models.Model):
    """Append-only event log for an OrchestrationRun.

    Move 2 of the strategic moves: orchestration must be event-sourced so we
    can replay/audit. Every step transition, retry, compensation, and external
    call emits a row here. Aggregates on OrchestrationRun stay correct because
    they are projections over these events.
    """

    class EventType(models.TextChoices):
        RUN_CREATED = "run_created", "Run created"
        RUN_STARTED = "run_started", "Run started"
        STEP_STARTED = "step_started", "Step started"
        STEP_SUCCEEDED = "step_succeeded", "Step succeeded"
        STEP_FAILED = "step_failed", "Step failed"
        RETRY_SCHEDULED = "retry_scheduled", "Retry scheduled"
        RUN_COMPLETED = "run_completed", "Run completed"
        RUN_FAILED = "run_failed", "Run failed"
        RUN_CANCELLED = "run_cancelled", "Run cancelled"
        COMPENSATION_STARTED = "compensation_started", "Compensation started"
        COMPENSATION_COMPLETED = "compensation_completed", "Compensation completed"

    run = models.ForeignKey(
        OrchestrationRun,
        on_delete=models.CASCADE,
        related_name="events",
    )
    sequence_number = models.PositiveIntegerField(
        help_text="Monotonic position within this run (1, 2, 3, ...).",
    )
    event_type = models.CharField(
        max_length=32,
        choices=EventType.choices,
        db_index=True,
    )
    step_name = models.CharField(max_length=120, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "orchestration"
        unique_together = [["run", "sequence_number"]]
        ordering = ["run", "sequence_number"]
        indexes = [
            models.Index(fields=["run", "event_type"], name="orch_evt_run_type_idx"),
        ]

    def __str__(self) -> str:
        return f"run={self.run_id} #{self.sequence_number} {self.event_type}"


class OrchestrationSLOMetric(models.Model):
    """Rolled-up SLO snapshot per definition per day.

    Populated by the `aggregate_orchestration_slos` management command (or its
    Celery wrapper). Each row carries p50/p95 latency, success rate, and
    queue depth so the operator workbench can render an SLO dashboard.
    """

    definition = models.ForeignKey(
        ProcessDefinition,
        on_delete=models.CASCADE,
        related_name="slo_metrics",
    )
    window_start = models.DateTimeField(db_index=True)
    window_end = models.DateTimeField()
    runs_total = models.PositiveIntegerField(default=0)
    runs_succeeded = models.PositiveIntegerField(default=0)
    runs_failed = models.PositiveIntegerField(default=0)
    runs_sla_breached = models.PositiveIntegerField(default=0)
    p50_latency_ms = models.PositiveIntegerField(default=0)
    p95_latency_ms = models.PositiveIntegerField(default=0)
    p99_latency_ms = models.PositiveIntegerField(default=0)
    queue_depth_max = models.PositiveIntegerField(default=0)
    success_rate = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "orchestration"
        unique_together = [["definition", "window_start"]]
        ordering = ["-window_start", "definition"]

    def __str__(self) -> str:
        return f"{self.definition.code} {self.window_start:%Y-%m-%d}"
