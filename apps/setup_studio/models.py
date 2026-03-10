"""
Setup Studio step models (metadata plan todo 7).
Step models capturing: institution basics, plan choice, blueprint selection, branding, starter stack, data path.
"""
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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "setup_studio"
        verbose_name = "Setup progress"
        verbose_name_plural = "Setup progress"
        unique_together = [["school"]]

    def __str__(self):
        return f"SetupProgress({self.school_id})"
