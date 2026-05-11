# Imports
from django.conf import settings
from django.db import models
from apps.academics.models import AcademicYear, Term
from apps.accounts.validators import validate_grade_import_file, validate_file_size_5mb
# --- Phase 8: AttendanceLog stub for dashboard metrics ---


class AttendanceLog(models.Model):
    date = models.DateField()
    status = models.CharField(max_length=20)
    # Add more fields as needed for real implementation

    class Meta:
        app_label = "analytics"


# ========== GRADE IMPORT JOB TRACKING ==========


def grade_import_job_upload_to(instance, filename):
    """Tenant-scoped path for GradeImportJob.uploaded_file (Section 25.3). School from academic_year."""
    ay = getattr(instance, "academic_year", None)
    school_id = getattr(ay, "school_id", None) if ay else None
    if school_id is None:
        return f"tenant_uploads/analytics/grade_imports/{filename}"
    return f"tenants/{school_id}/analytics/grade_imports/{filename}"


class GradeImportJob(models.Model):
    """Tracks a single bulk grade import session."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("validating", "Validating"),
        ("preview", "Preview Ready"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial", "Partially Completed"),
    ]

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="grade_import_jobs"
    )
    term = models.ForeignKey(
        Term, on_delete=models.CASCADE, related_name="grade_import_jobs"
    )
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="grade_imports_uploaded",
    )
    uploaded_file = models.FileField(
        upload_to=grade_import_job_upload_to,
        null=True,
        blank=True,
        validators=[validate_grade_import_file, validate_file_size_5mb],
    )
    file_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    started_processing_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Results
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    error_log = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["academic_year", "term", "-created_at"]),
        ]

    def __str__(self):
        return f"Import {self.academic_year}/{self.term} - {self.status}"


# ========== Phase 4: AI benchmarking (anonymized regional aggregates) ==========


class BenchmarkAggregate(models.Model):
    """
    Anonymized aggregate metrics per region/sub_system/subject/term.
    ETL job populates from Evaluation/ReportCard; no school or student identifiers.
    """

    region_code = models.CharField(max_length=20, db_index=True)
    sub_system = models.CharField(max_length=10, db_index=True)
    subject_id = models.IntegerField(null=True, blank=True, db_index=True)
    term_id = models.IntegerField(null=True, blank=True, db_index=True)
    academic_year_id = models.IntegerField(null=True, blank=True, db_index=True)
    metric = models.CharField(max_length=60)
    value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    sample_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["region_code", "sub_system", "metric"]
        indexes = [
            models.Index(fields=["region_code", "sub_system", "metric"]),
        ]

    def __str__(self):
        return f"{self.region_code}/{self.sub_system} {self.metric}={self.value} (n={self.sample_size})"


# ========== Predictive Engine: At-Risk Dashboard & Intervention (Plan XVIII–XIX) ==========


class RiskFactor(models.Model):
    """
    Nightly-computed at-risk score per student (0–100). Red 80–100, Amber 50–79, Green 0–49.
    Explainable: reason_summary gives "why" (e.g. "High absenteeism (4 days) + dropping grades in Science").
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="risk_factors",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="risk_factors",
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="0–100 risk score",
    )
    reason_summary = models.CharField(
        max_length=500,
        blank=True,
        help_text="AI-generated short summary for 'Why' column.",
    )
    model_version = models.CharField(
        max_length=80,
        blank=True,
        help_text="ML model name@version used for this score (Phase 9 registry).",
    )
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "-computed_at"]
        indexes = [
            models.Index(fields=["school", "-computed_at"]),
            models.Index(fields=["school", "student"]),
        ]
        get_latest_by = "computed_at"

    def __str__(self):
        return f"{self.student_id} score={self.score} ({self.computed_at.date()})"

    @property
    def band(self):
        """Red / Amber / Green for heat map, using the school's RiskThresholds when defined.

        Falls back to 80 / 50 if no per-tenant thresholds have been set so the heat map
        continues to render rather than silently flatlining to green.
        """
        s = float(self.score)
        red_min = 80.0
        amber_min = 50.0
        try:
            thresholds = getattr(self.school, "risk_thresholds", None)
        except (AttributeError, ValueError):
            thresholds = None
        if thresholds is not None:
            try:
                red_min = float(getattr(thresholds, "red_min", red_min))
                amber_min = float(getattr(thresholds, "amber_min", amber_min))
            except (TypeError, ValueError):
                pass
        if s >= red_min:
            return "red"
        if s >= amber_min:
            return "amber"
        return "green"


class RiskThresholds(models.Model):
    """
    Plan XVII: Per-tenant risk band thresholds (0–100).
    When score >= red_min → Red; when score >= amber_min → Amber; else Green.
    """

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="risk_thresholds",
    )
    amber_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        help_text="Score >= this → Amber band",
    )
    red_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=80,
        help_text="Score >= this → Red band",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Risk thresholds"
        verbose_name_plural = "Risk thresholds"

    def __str__(self):
        return f"{self.school_id} Amber>={self.amber_min} Red>={self.red_min}"


def get_risk_band_for_school(score, school):
    """Return 'red' | 'amber' | 'green' using school's RiskThresholds if set, else platform defaults.

    The fallback thresholds live in settings.RISK_BAND_RED_MIN / RISK_BAND_AMBER_MIN so
    they can be tuned per deployment without code changes (and so a tenant on a 0-20
    grading scale can switch the platform default rather than getting every student
    flagged red).
    """
    s = float(score)
    try:
        th = RiskThresholds.objects.get(school=school)
        red_min = float(th.red_min)
        amber_min = float(th.amber_min)
    except RiskThresholds.DoesNotExist:
        from django.conf import settings as _settings

        red_min = float(getattr(_settings, "RISK_BAND_RED_MIN", 80))
        amber_min = float(getattr(_settings, "RISK_BAND_AMBER_MIN", 50))
    if s >= red_min:
        return "red"
    if s >= amber_min:
        return "amber"
    return "green"


class InterventionLog(models.Model):
    """Audit trail for automated or manual interventions (Amber/Red levels). Plan XIX: Action Center."""

    class Status(models.TextChoices):
        ONGOING = "ONGOING", "Ongoing"
        RESOLVED = "RESOLVED", "Resolved"
        DISMISSED = "DISMISSED", "Dismissed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="intervention_logs",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="intervention_logs",
    )
    trigger_reason = models.CharField(max_length=255)
    action_taken = models.CharField(
        max_length=100,
        help_text="e.g. Email, Meeting, Resource",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ONGOING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dismissed_interventions",
    )
    draft_email_subject = models.CharField(max_length=255, blank=True)
    draft_email_body = models.TextField(blank=True)
    meeting_link = models.URLField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self):
        return f"{self.student_id} — {self.action_taken} ({self.status})"


# ========== Plan XVIII: StudentSignals (time-series for risk scoring) ==========


class StudentSignals(models.Model):
    """
    Time-series signals per student for tenant-scoped risk scoring: attendance ratio,
    grade deltas, login gaps, submission latency. Pipeline (tasks/signals) writes here;
    nightly RiskFactor task can optionally consume this for explainability.
    """

    class SignalType(models.TextChoices):
        ATTENDANCE_RATIO_30D = "attendance_ratio_30d", "Attendance ratio (30 days)"
        GRADE_DELTA = "grade_delta", "Grade delta vs prior term"
        LOGIN_GAP_DAYS = "login_gap_days", "Days since last login"
        SUBMISSION_LATENCY_DAYS = (
            "submission_latency_days",
            "Assignment submission latency",
        )

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="student_signals",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="signals",
    )
    signal_type = models.CharField(
        max_length=40, choices=SignalType.choices, db_index=True
    )
    value = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Numeric value (e.g. 0.85 for 85% attendance, -5 for grade drop).",
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional extra context (e.g. subject_id, term_id, counts).",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["school", "student", "signal_type"]),
            models.Index(fields=["school", "-recorded_at"]),
        ]
        verbose_name = "Student signal"
        verbose_name_plural = "Student signals"

    def __str__(self):
        return f"{self.student_id} {self.signal_type}={self.value} @ {self.recorded_at}"


# ========== Phase 9: ML registry (versioned models, inference) ==========


class MLModel(models.Model):
    """
    Registry of deployed ML models: name, version, artifact path or config, input/output schema.
    Inference layer loads active model and runs prediction (e.g. risk score).
    """

    MODEL_TYPES = [
        ("risk", "Risk scoring"),
        ("forecast", "Enrollment/forecast"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=120, db_index=True)
    version = models.CharField(max_length=40, db_index=True)
    model_type = models.CharField(max_length=20, choices=MODEL_TYPES, default="risk")
    artifact_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path or blob reference to serialized model (e.g. S3 key, file path).",
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Config for loading/running (e.g. threshold, feature list).",
    )
    input_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="Expected input keys/types for inference.",
    )
    output_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="Output keys (e.g. score, label).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only one active per (name, model_type) should be True.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("name", "version")]
        indexes = [
            models.Index(fields=["model_type", "is_active"]),
        ]
        verbose_name = "ML model"
        verbose_name_plural = "ML models"

    def __str__(self):
        return f"{self.name}@{self.version} ({self.model_type})"


class StudentAtRiskSignal(models.Model):
    """BR-06 EWS v1: at-risk score + factors for intervention workflow."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_INTERVENTION = "in_intervention", "In intervention"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="at_risk_signals",
    )
    student_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="at_risk_signals",
    )
    score = models.FloatField(
        default=0.0,
        help_text="Higher = more at-risk (0–100 scale).",
    )
    factors = models.JSONField(
        default=dict,
        blank=True,
        help_text="e.g. attendance_pct, grade_trend, flags.",
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="at_risk_signals_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score", "-updated_at"]
        indexes = [
            models.Index(fields=["school", "status", "-score"]),
        ]
        verbose_name = "Student at-risk signal (EWS)"
        verbose_name_plural = "Student at-risk signals (EWS)"

    def __str__(self):
        return f"{self.school_id}:{self.student_user_id}:{self.score:.1f}"


class GovernedSavedReport(models.Model):
    """
    Tenant-scoped saved governed query definitions (ORM catalog only — never raw SQL).
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="governed_saved_reports",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="governed_saved_reports",
    )
    name = models.CharField(max_length=200)
    definition = models.JSONField(
        default=dict,
        help_text="Allowed keys: dataset_id, fields, filters, group_by, aggregate, limit.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(
                fields=["school", "-updated_at"],
                name="analytics_gsr_sch_upd_idx",
            ),
        ]
        verbose_name = "Governed saved report"
        verbose_name_plural = "Governed saved reports"

    def __str__(self) -> str:
        return f"{self.name} ({self.school_id})"
