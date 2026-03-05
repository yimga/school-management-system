"""
Workflow catalog (Part 2c): WorkflowTemplate and TenantWorkflow.

Pre-built business workflows (e.g. "If absent 3 days → notify counselor") with
trigger–condition–action. WorkflowConfig in academics remains for wizards.
"""
from django.db import models


class WorkflowTemplate(models.Model):
    """
    Master workflow definition (public/control schema). Trigger, conditions, actions (JSON).
    Pre-built e.g. "Safety Net", "Fiscal Guardian". TenantWorkflow links a school to a template.
    """

    code = models.CharField(max_length=80, unique=True, help_text="Unique code (e.g. safety_net_absent_3d)")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    trigger = models.CharField(
        max_length=80,
        blank=True,
        help_text="Trigger type: scheduled, event, manual, webhook, etc.",
    )
    trigger_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Trigger configuration (e.g. cron, event name).",
    )
    conditions = models.JSONField(
        default=list,
        blank=True,
        help_text="List of conditions: [{\"field\": \"...\", \"op\": \"eq\", \"value\": \"...\"}].",
    )
    actions = models.JSONField(
        default=list,
        blank=True,
        help_text="List of actions: [{\"type\": \"notify\", \"params\": {...}}].",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Workflow Template"
        verbose_name_plural = "Workflow Templates"
        ordering = ["code"]

    def __str__(self):
        return f"{self.name} [{self.code}]"


class TenantWorkflow(models.Model):
    """
    Per-school activation of a WorkflowTemplate (public schema; school FK).
    Overrides (e.g. action params) and is_active. Execution engine runs active tenant workflows.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="workflow_assignments",
    )
    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.PROTECT,
        related_name="tenant_assignments",
    )
    overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text="Override trigger_config, conditions, or action params for this school.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant Workflow"
        verbose_name_plural = "Tenant Workflows"
        unique_together = [["school", "template"]]
        ordering = ["school", "template"]

    def __str__(self):
        return f"{self.school.name} — {self.template.name}"


class WorkflowRunLog(models.Model):
    """
    Audit log for each workflow run (first-class workflow engine).
    One row per run; stores conditions_passed, actions_run summary, context keys (no PII).
    """

    tenant_workflow = models.ForeignKey(
        TenantWorkflow,
        on_delete=models.CASCADE,
        related_name="run_logs",
    )
    conditions_passed = models.BooleanField(default=False)
    actions_run = models.JSONField(default=list, help_text="List of {type, params, run_at} per action.")
    context_keys = models.JSONField(default=list, help_text="Keys present in context (no values for privacy).")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Workflow Run Log"
        verbose_name_plural = "Workflow Run Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Run {self.id} — {self.tenant_workflow} @ {self.created_at}"
