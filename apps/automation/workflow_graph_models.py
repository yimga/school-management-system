"""
Salesforce-style visual workflow graph (relational).

Compiled into condition/action DSL consumed by ``apps.siteconfig.workflow_engine``.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Workflow(models.Model):
    """Tenant-scoped automation workflow (graph composed of nodes + edges)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        PAUSED = "paused", "Paused"
        FAILED = "failed", "Failed"
        ARCHIVED = "archived", "Archived"

    class Trigger(models.TextChoices):
        ATTENDANCE_MARKED = "attendance_marked", "Attendance marked"
        ATTENDANCE_SAVED = "attendance_saved", "Attendance saved (platform)"
        MARKS_SUBMITTED = "marks_submitted", "Marks submitted"
        PAYMENT_RECEIVED = "payment_received", "Payment received"
        PAYMENT_SUCCESS = "payment_success", "Payment succeeded"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        STUDENT_CREATED = "student_created", "Student added"
        REPORT_GENERATED = "report_generated", "Report generated"
        STUDENT_RISK_DETECTED = "student_risk_detected", "Student risk detected"
        APP_INSTALLED = "app_installed", "Marketplace app installed"
        OFFLINE_ACTION_CONFLICT = (
            "offline_action_conflict",
            "Offline sync action conflict",
        )

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="visual_workflows",
    )
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    trigger_event = models.CharField(
        max_length=48,
        choices=Trigger.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["school_id", "name"]
        indexes = [
            models.Index(fields=["school", "trigger_event", "status"]),
        ]
        verbose_name = "Visual workflow"
        verbose_name_plural = "Visual workflows"

    def __str__(self) -> str:
        return f"{self.name} ({self.trigger_event})"


class WorkflowNode(models.Model):
    """Single node in the canvas (trigger | condition | action | delay)."""

    class Kind(models.TextChoices):
        TRIGGER = "trigger", "Trigger"
        CONDITION = "condition", "Condition"
        ACTION = "action", "Action"
        DELAY = "delay", "Delay"

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="nodes",
    )
    external_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Stable client id from the visual builder.",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, db_index=True)
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Kind-specific payload (conditions, action params, delay seconds).",
    )
    position = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional {x,y} for canvas persistence.",
    )

    class Meta:
        ordering = ["workflow_id", "external_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["workflow", "external_id"],
                name="automation_workflownode_unique_external",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} ({self.external_id})"


class WorkflowEdge(models.Model):
    """Directed edge between two nodes."""

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="edges",
    )
    source = models.ForeignKey(
        WorkflowNode,
        on_delete=models.CASCADE,
        related_name="out_edges",
    )
    target = models.ForeignKey(
        WorkflowNode,
        on_delete=models.CASCADE,
        related_name="in_edges",
    )
    label = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["workflow", "source"]),
            models.Index(fields=["workflow", "target"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_id}→{self.target_id}"


class WorkflowRunLog(models.Model):
    """Execution audit for :func:`apps.automation.visual_executor.run_workflow`."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="run_logs",
    )
    trigger_event = models.CharField(max_length=48, blank=True)
    conditions_passed = models.BooleanField(default=False)
    dry_run = models.BooleanField(default=False)
    payload_snapshot = models.JSONField(default=dict, blank=True)
    actions_run = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SUCCESS,
        db_index=True,
    )
    error_message = models.TextField(blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visual_workflow_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"WorkflowRun {self.pk} wf={self.workflow_id}"
