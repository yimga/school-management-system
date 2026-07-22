"""Platform-wide WorkflowRun + WorkflowStep models (v4.00.96).

The Workflow Progress Bus emits live progress for every platform workflow that
opts in via the ``@track_workflow(...)`` decorator: user creation, tenant
creation/deletion, school setup, OneRoster bulk imports, OAuth exchange, etc.

Design:

* ``WorkflowRun`` is the parent envelope — one row per logical workflow
  invocation. Carries tenant_schema + school_id + actor_user_id for scoping,
  status + heartbeat for stuck-detection, and ``suggested_remediation`` JSON
  for the AI auto-fix card surfaced in the frontend chip.
* ``WorkflowStep`` is one row per granular step inside a run, ordered by
  ``ordinal``. Lets the frontend draw a "step train" with done / current /
  pending beads + per-step duration.
* Both models carry ``payload_summary`` JSON that the writer side scrubs
  against the platform's secret-key denylist (see ``workflow_tracker``).
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q


class WorkflowRunStatus(models.TextChoices):
    """Status FSM for a workflow run.

    Transitions:
      RUNNING → SUCCEEDED        (happy path)
      RUNNING → FAILED           (caught exception or explicit fail())
      RUNNING → STUCK            (no heartbeat within expected window × 1.5)
      RUNNING → CANCELLED        (operator cancel via UI)
      STUCK   → RUNNING          (heartbeat resumed)
      STUCK   → FAILED           (operator force-fail after diagnosis)
    """

    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    STUCK = "stuck", "Stuck"
    CANCELLED = "cancelled", "Cancelled"


class WorkflowStepStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class WorkflowRun(models.Model):
    """One platform workflow invocation.

    ``workflow_key`` references the SOT in
    ``apps.platform_runtime.workflow_registry.WORKFLOWS`` when known. Unknown
    keys are accepted (free-form CharField) so ad-hoc invocations don't fail
    the writer side — the resolver downgrades gracefully when no definition
    matches.
    """

    workflow_key = models.CharField(max_length=80, db_index=True)
    workflow_label = models.CharField(max_length=160, blank=True, default="")  # magic-number-allow: charfield-max-length
    tenant_schema = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    school_id = models.CharField(max_length=40, blank=True, default="", db_index=True)
    actor_user_id = models.CharField(max_length=40, blank=True, default="", db_index=True)
    actor_label = models.CharField(max_length=120, blank=True, default="")

    status = models.CharField(
        max_length=16,
        choices=WorkflowRunStatus.choices,
        default=WorkflowRunStatus.RUNNING,
        db_index=True,
    )

    total_steps = models.PositiveSmallIntegerField(default=0)
    current_step_ordinal = models.PositiveSmallIntegerField(default=0)
    current_step_name = models.CharField(max_length=80, blank=True, default="")

    expected_duration_seconds = models.PositiveIntegerField(default=30)

    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_heartbeat_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    idempotency_key = models.CharField(
        max_length=128, blank=True, default="", db_index=True
    )

    payload_summary = models.JSONField(default=dict, blank=True)
    error_summary = models.JSONField(default=dict, blank=True)
    suggested_remediation = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Workflow run"
        verbose_name_plural = "Workflow runs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(
                fields=["tenant_schema", "status", "-started_at"],
                name="wfr_tenant_status_started_idx",
            ),
            models.Index(
                fields=["workflow_key", "-started_at"],
                name="wfr_workflow_started_idx",
            ),
            models.Index(
                fields=["actor_user_id", "-started_at"],
                name="wfr_actor_started_idx",
            ),
            models.Index(
                fields=["last_heartbeat_at"],
                name="wfr_heartbeat_idx",
            ),
        ]
        constraints = [
            # One active provision run per school (zombie dual-card seal).
            models.UniqueConstraint(
                fields=["school_id", "workflow_key"],
                condition=Q(status__in=["running", "stuck"])
                & ~Q(school_id="")
                & Q(
                    workflow_key__in=[
                        "tenant_school_provision",
                        "tenant_school_create",
                    ]
                ),
                name="uniq_active_provision_run_per_school",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.workflow_key}[{self.status}] tenant={self.tenant_schema or '-'}"


class WorkflowStep(models.Model):
    """One step inside a WorkflowRun. Append-only by convention (no UPDATE
    on done/failed rows; only status mutates while RUNNING)."""

    run = models.ForeignKey(
        WorkflowRun,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    ordinal = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80)
    label = models.CharField(max_length=160, blank=True, default="")  # magic-number-allow: charfield-max-length

    status = models.CharField(
        max_length=12,
        choices=WorkflowStepStatus.choices,
        default=WorkflowStepStatus.PENDING,
        db_index=True,
    )

    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    payload_summary = models.JSONField(default=dict, blank=True)
    error_text = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Workflow step"
        verbose_name_plural = "Workflow steps"
        ordering = ["run_id", "ordinal"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "ordinal"],
                name="wfs_unique_run_ordinal",
            ),
        ]
        indexes = [
            models.Index(
                fields=["run", "status"],
                name="wfs_run_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.run_id}#{self.ordinal} {self.name}[{self.status}]"
