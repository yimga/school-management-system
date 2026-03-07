"""
Section 11: Category killers — Benchmark intelligence (11.3), Customer success (11.4).

11.3: Peer benchmarking, operational maturity scoring, forecast scenarios, risk alerts, intervention suggestions.
11.4: Tenant health scores, workflow failure detection, admin inactivity alerts, support co-pilot, guided onboarding,
      shadow sessions with masking, auto-ticket creation.
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


# ---------- 11.3 Benchmark intelligence ----------


class BenchmarkCohort(models.Model):
    """
    Peer group definition for benchmarking: by region, size band, institution type.
    Used to compare a tenant against peers (e.g. same country, similar student count).
    """
    class SizeBand(models.TextChoices):
        MICRO = "micro", "Micro (< 100)"
        SMALL = "small", "Small (100–500)"
        MEDIUM = "medium", "Medium (500–2000)"
        LARGE = "large", "Large (2000+)"

    name = models.CharField(max_length=120, help_text="Display name, e.g. 'Private K12 Cameroon'")
    country_code = models.CharField(max_length=10, blank=True, db_index=True)
    region_code = models.CharField(max_length=20, blank=True, db_index=True)
    size_band = models.CharField(max_length=20, choices=SizeBand.choices, blank=True, db_index=True)
    institution_type = models.CharField(max_length=60, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "customersuccess"
        ordering = ["name"]
        verbose_name = "Benchmark cohort"
        verbose_name_plural = "Benchmark cohorts"

    def __str__(self):
        return self.name


class TenantMaturityScore(models.Model):
    """
    Operational maturity score per tenant (and optionally per dimension).
    Computed by background job or on-demand; stored for history and peer comparison.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="maturity_scores",
    )
    dimension = models.CharField(
        max_length=60,
        db_index=True,
        help_text="e.g. admissions, finance, academics, compliance, adoption",
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0–100",
    )
    payload = models.JSONField(default=dict, blank=True, help_text="Breakdown or evidence keys")
    computed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-computed_at"]
        indexes = [models.Index(fields=["school", "dimension", "-computed_at"])]
        verbose_name = "Tenant maturity score"
        verbose_name_plural = "Tenant maturity scores"

    def __str__(self):
        return f"{self.school_id} {self.dimension}={self.score} @ {self.computed_at.date()}"


class ForecastScenario(models.Model):
    """
    Stored forecast scenario per tenant (e.g. enrollment, revenue, capacity).
    Used for what-if and risk alerts.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="forecast_scenarios",
    )
    scenario_type = models.CharField(max_length=60, db_index=True)
    label = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Forecast scenario"
        verbose_name_plural = "Forecast scenarios"

    def __str__(self):
        return f"{self.school_id} {self.scenario_type} @ {self.created_at.date()}"


class TenantRiskAlert(models.Model):
    """
    Tenant-level risk alert (amber/red): low adoption, payment issues, workflow failures, etc.
    Drives intervention suggestions and optional auto-ticket.
    """
    class Severity(models.TextChoices):
        AMBER = "amber", "Amber"
        RED = "red", "Red"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="risk_alerts",
    )
    severity = models.CharField(max_length=20, choices=Severity.choices, db_index=True)
    reason = models.CharField(max_length=255)
    suggested_action = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Tenant risk alert"
        verbose_name_plural = "Tenant risk alerts"

    def __str__(self):
        return f"{self.school_id} {self.severity}: {self.reason}"


class TenantInterventionSuggestion(models.Model):
    """
    Suggested intervention for a tenant (e.g. enable module, run onboarding, contact CS).
    Can be generated from risk alerts or maturity gaps.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="intervention_suggestions",
    )
    category = models.CharField(max_length=60, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.PositiveSmallIntegerField(default=5, help_text="1=highest")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["priority", "-created_at"]
        verbose_name = "Tenant intervention suggestion"
        verbose_name_plural = "Tenant intervention suggestions"

    def __str__(self):
        return f"{self.school_id} [{self.category}] {self.title}"


# ---------- 11.4 Customer success ----------


class TenantHealthScore(models.Model):
    """
    Stored tenant health score (0–100) and dimension breakdown.
    Computed by service from last_activity, workflow failures, adoption, etc.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="health_scores",
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0–100 overall health",
    )
    dimensions = models.JSONField(
        default=dict,
        blank=True,
        help_text="e.g. {activity: 80, workflows: 70, adoption: 60}",
    )
    computed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-computed_at"]
        indexes = [models.Index(fields=["school", "-computed_at"])]
        verbose_name = "Tenant health score"
        verbose_name_plural = "Tenant health scores"

    def __str__(self):
        return f"{self.school_id} health={self.score} @ {self.computed_at.date()}"


class WorkflowFailureEvent(models.Model):
    """
    Record of a workflow run that had one or more failed actions.
    Populated from workflow engine or async processor; used for health and auto-ticket.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="workflow_failure_events",
    )
    workflow_name = models.CharField(max_length=120, db_index=True)
    workflow_run_id = models.CharField(max_length=100, blank=True, db_index=True)
    error_summary = models.CharField(max_length=500)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Workflow failure event"
        verbose_name_plural = "Workflow failure events"

    def __str__(self):
        return f"{self.school_id} {self.workflow_name} @ {self.created_at.isoformat()}"


class AdminInactivityAlert(models.Model):
    """
    Alert when no admin activity for a tenant for longer than threshold (e.g. 14 days).
    Can trigger notification and optional auto-ticket.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="admin_inactivity_alerts",
    )
    last_admin_activity = models.DateTimeField()
    threshold_days = models.PositiveSmallIntegerField(default=14)
    created_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    ticket_created = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Admin inactivity alert"
        verbose_name_plural = "Admin inactivity alerts"

    def __str__(self):
        return f"{self.school_id} inactive since {self.last_admin_activity.date()}"


class AutoTicketRule(models.Model):
    """
    Rule for when to auto-create a support ticket (e.g. on workflow failure, health below X, inactivity).
    """
    class Trigger(models.TextChoices):
        WORKFLOW_FAILURE = "workflow_failure", "Workflow failure"
        HEALTH_BELOW = "health_below", "Health score below threshold"
        INACTIVITY_DAYS = "inactivity_days", "Admin inactivity (days)"
        RISK_ALERT_RED = "risk_alert_red", "Red risk alert"

    name = models.CharField(max_length=120)
    trigger = models.CharField(max_length=40, choices=Trigger.choices, db_index=True)
    config = models.JSONField(default=dict, help_text="e.g. {threshold: 50} for health_below")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Auto-ticket rule"
        verbose_name_plural = "Auto-ticket rules"

    def __str__(self):
        return f"{self.name} ({self.get_trigger_display()})"
