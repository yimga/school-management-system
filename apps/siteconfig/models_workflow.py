"""
Workflow catalog (Part 2c): WorkflowTemplate and TenantWorkflow.

Pre-built business workflows (e.g. "If absent 3 days → notify counselor") with
trigger–condition–action (Section 5: Trigger → Conditions → Actions → Approvals → Audit).
Level 1 = locked global default, Level 2 = configurable template, Level 3 = constrained custom.
"""

from django.db import models


class WorkflowPack(models.Model):
    """
    Phase 4: Reusable workflow pack (e.g. Admissions Standard, Finance Dual Approval).
    Groups WorkflowTemplates; assignable by module to a school.
    """

    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    family = models.CharField(max_length=64, blank=True, db_index=True)
    version = models.CharField(max_length=32, default="1.0")
    is_active = models.BooleanField(default=True, db_index=True)
    recommended_sectors = models.JSONField(
        default=list,
        blank=True,
        help_text="Wedge 14–22 sector codes (e.g. PUBLIC, NGO) this pack is recommended for.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Workflow Pack"
        verbose_name_plural = "Workflow Packs"
        ordering = ["family", "name"]

    def __str__(self):
        return f"{self.name} [{self.code}]"


class WorkflowPackAssignment(models.Model):
    """Assign a WorkflowPack to a school for a given module (e.g. admissions, fee_approval)."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="workflow_pack_assignments",
    )
    workflow_pack = models.ForeignKey(
        WorkflowPack,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    module_slug = models.CharField(
        max_length=80,
        db_index=True,
        help_text="e.g. admissions, fee_approval, grade_publish",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Workflow pack assignment"
        verbose_name_plural = "Workflow pack assignments"
        unique_together = [["school", "module_slug"]]
        ordering = ["school", "module_slug"]


class WorkflowTemplate(models.Model):
    """
    Master workflow definition (public/control schema). Trigger, conditions, actions (JSON).
    Pre-built e.g. "Safety Net", "Fiscal Guardian". TenantWorkflow links a school to a template.
    Section 5: level 1 = locked, 2 = configurable template, 3 = constrained custom.
    """

    class Level(models.IntegerChoices):
        LOCKED = 1, "Level 1: Locked global default (safety/legal)"
        CONFIGURABLE_TEMPLATE = (
            2,
            "Level 2: Configurable template (tenant chooses approved variants)",
        )
        CONSTRAINED_CUSTOM = (
            3,
            "Level 3: Constrained custom (tenant customizes within safe boundaries)",
        )

    code = models.CharField(
        max_length=80, unique=True, help_text="Unique code (e.g. safety_net_absent_3d)"
    )
    workflow_pack = models.ForeignKey(
        WorkflowPack,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="templates",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    level = models.PositiveSmallIntegerField(
        choices=Level.choices,
        default=Level.CONFIGURABLE_TEMPLATE,
        help_text="Section 5: 1=locked, 2=configurable template, 3=constrained custom.",
    )
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
        help_text='List of conditions: [{"field": "...", "op": "eq", "value": "..."}].',
    )
    actions = models.JSONField(
        default=list,
        blank=True,
        help_text='List of actions: [{"type": "notify", "params": {...}}].',
    )
    is_active = models.BooleanField(default=True)
    certified = models.BooleanField(
        default=False,
        help_text="Section 5.6: Certified pack — platform-provided, safe to activate.",
    )
    version = models.CharField(
        max_length=32,
        blank=True,
        default="1.0",
        help_text="Declarative version for upgrade-safety and rollback.",
    )
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
    actions_run = models.JSONField(
        default=list, help_text="List of {type, params, run_at} per action."
    )
    context_keys = models.JSONField(
        default=list, help_text="Keys present in context (no values for privacy)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Workflow Run Log"
        verbose_name_plural = "Workflow Run Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Run {self.id} — {self.tenant_workflow} @ {self.created_at}"
