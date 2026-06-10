"""Workflow Progress 10x — autopilot policy, duration rollups, SLA breach log."""

from __future__ import annotations

from django.db import models


class WorkflowAutopilotPolicy(models.Model):
    """Per-workflow (optional per-tenant) allowlist for unattended auto-fix kinds."""

    workflow_key = models.CharField(max_length=80, db_index=True)
    tenant_schema = models.CharField(max_length=64, blank=True, default="", db_index=True)
    allowed_auto_fix_kinds = models.JSONField(default=list, blank=True)
    enabled = models.BooleanField(default=False)
    promoted_from_successes = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Workflow autopilot policy"
        verbose_name_plural = "Workflow autopilot policies"
        constraints = [
            models.UniqueConstraint(
                fields=("workflow_key", "tenant_schema"),
                name="uniq_workflow_autopilot_policy_scope",
            )
        ]

    def __str__(self) -> str:
        scope = self.tenant_schema or "*"
        return f"{self.workflow_key}@{scope}"


class WorkflowAutopilotApplyLog(models.Model):
    """Audit trail for manual and autopilot fix applications."""

    run_id = models.PositiveIntegerField(db_index=True)
    workflow_key = models.CharField(max_length=80, db_index=True)
    auto_fix_kind = models.CharField(max_length=64)
    outcome = models.CharField(max_length=32, default="applied")
    actor_user_id = models.CharField(max_length=40, blank=True, default="")
    autopilot = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Workflow autopilot apply log"
        verbose_name_plural = "Workflow autopilot apply logs"
        ordering = ["-created_at"]


class HealthRemediationLog(models.Model):
    """School-attributed audit trail for the health self-healing engine.

    Records autonomous applies and (when explicitly captured) shadow proposals, so
    operators can review what the engine sees and what it did BEFORE enabling apply.
    Distinct from ``WorkflowAutopilotApplyLog`` (which has no school field) because
    autonomous action on a live tenant demands tenant-attributed forensics.
    """

    school = models.ForeignKey(
        "schools.School",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="health_remediation_logs",
    )
    school_slug = models.CharField(max_length=80, blank=True, default="", db_index=True)
    signal = models.CharField(max_length=80, db_index=True)
    kind = models.CharField(max_length=64, blank=True, default="")
    source = models.CharField(max_length=16, default="rule")  # rule | ai
    confidence = models.FloatField(default=0.0)
    mode = models.CharField(max_length=16, default="shadow")  # shadow | apply
    outcome = models.CharField(max_length=24, default="proposed")  # proposed|applied|failed|skipped
    reversible = models.BooleanField(default=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Health remediation log"
        verbose_name_plural = "Health remediation logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school_slug", "created_at"]),
            models.Index(fields=["mode", "outcome"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind or self.signal}@{self.school_slug or '-'}:{self.outcome}"


class WorkflowDurationStat(models.Model):
    """Rolling duration rollup per workflow_key for predictive degrading."""

    workflow_key = models.CharField(max_length=80, unique=True)
    sample_count = models.PositiveIntegerField(default=0)
    p50_seconds = models.PositiveIntegerField(default=0)
    p95_seconds = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Workflow duration stat"
        verbose_name_plural = "Workflow duration stats"


class WorkflowSlaBreach(models.Model):
    """Operator-visible SLA breach when a run exceeds registry slo_seconds."""

    run_id = models.PositiveIntegerField(db_index=True)
    workflow_key = models.CharField(max_length=80, db_index=True)
    tenant_schema = models.CharField(max_length=64, blank=True, default="")
    slo_seconds = models.PositiveIntegerField()
    actual_seconds = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Workflow SLA breach"
        verbose_name_plural = "Workflow SLA breaches"
        ordering = ["-created_at"]
