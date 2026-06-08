"""Setup Studio state for institution, plan, blueprint, brand, and data setup."""

from django.db import models


class SetupStepDefinition(models.Model):
    """Master definition of a setup step (platform-wide)."""

    key = models.CharField(max_length=80, unique=True, db_index=True)
    label = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    link = models.CharField(max_length=512, blank=True)
    step_group = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text="e.g. institution_basics, plan_choice, blueprint, branding, starter_stack, data_path",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "setup_studio"
        ordering = ["order", "key"]

    def __str__(self):
        return f"{self.key}"


class SetupProgress(models.Model):
    """Per-school setup progress: which steps are done, current step."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="setup_progress",
    )
    current_step_key = models.CharField(max_length=80, blank=True, db_index=True)
    completed_keys = models.JSONField(
        default=list,
        blank=True,
        help_text="List of step keys marked done.",
    )
    step_state = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured state for each setup step.",
    )
    recommendations = models.JSONField(
        default=list,
        blank=True,
        help_text="Recommended actions and blueprint/starter-stack suggestions.",
    )
    role_previews = models.JSONField(
        default=list,
        blank=True,
        help_text="Role-specific preview destinations and summary cards.",
    )
    launch_checklist = models.JSONField(
        default=list,
        blank=True,
        help_text="Launch readiness checklist with blocker flags.",
    )
    launch_blockers = models.JSONField(
        default=list,
        blank=True,
        help_text="Current blocker keys preventing launch.",
    )
    health_score = models.PositiveSmallIntegerField(default=0)
    health_breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text="Weighted readiness scoring breakdown.",
    )
    launch_ready = models.BooleanField(default=False)
    launched_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "setup_studio"
        verbose_name = "Setup progress"
        verbose_name_plural = "Setup progress"
        unique_together = [["school"]]

    def __str__(self):
        return f"SetupProgress({self.school_id})"
