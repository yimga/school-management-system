from django.core.exceptions import ValidationError
from django.db import models, DatabaseError
from django.core.exceptions import ObjectDoesNotExist
from apps.academics.models import AcademicYear, Term, Classroom
from apps.people.models import StudentProfile
from apps.accounts.models import User
from apps.platform_runtime.structured_logging import log_exception_with_context


def reportcard_pdf_upload_to(instance, filename):
    """Tenant-scoped path for ReportCard.pdf_file (Section 25.3, media_tenant_scope.md)."""
    school_id = getattr(instance, "school_id", None) or (
        getattr(getattr(instance, "school", None), "pk", None)
        if getattr(instance, "school", None)
        else None
    )
    if school_id is None:
        return f"tenant_uploads/reports/reportcards/{filename}"
    return f"tenants/{school_id}/reports/reportcards/{filename}"


class TermPublishStatus(models.Model):
    """
    If classroom is NULL, it means published for the entire school for that term.
    If classroom is set, publish applies only to that class.
    """

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="publish_statuses"
    )
    term = models.ForeignKey(
        Term, on_delete=models.CASCADE, related_name="publish_statuses"
    )
    classroom = models.ForeignKey(
        Classroom,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="publish_statuses",
    )

    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="publishes"
    )

    class Meta:
        unique_together = ("academic_year", "term", "classroom")

    def __str__(self):
        scope = self.classroom.name if self.classroom else "Whole school"
        return f"{self.academic_year} {self.term.label} - {scope}: {'PUBLISHED' if self.is_published else 'NOT'}"


class ReportCard(models.Model):
    class Type(models.TextChoices):
        TERM = "TERM", "Term"
        ANNUAL = "ANNUAL", "Annual"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="report_cards",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="report_cards"
    )
    term = models.ForeignKey(
        Term,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="report_cards",
    )
    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="report_cards"
    )

    type = models.CharField(max_length=10, choices=Type.choices)
    pdf_file = models.FileField(
        upload_to=reportcard_pdf_upload_to, null=True, blank=True
    )
    generated_at = models.DateTimeField(auto_now=True)

    # Localization fields
    language = models.CharField(
        max_length=10, default="en", help_text="Language for certificate generation"
    )
    region_code = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text="Region code for score conversion",
    )

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.student} - {self.type} - {self.academic_year}"

    def get_language(self):
        """Get language for this report card."""
        if self.language:
            return self.language
        # Fall back to region-configured language
        if self.region_code:
            try:
                from apps.global_registries.models import RegionConfig

                region = (
                    RegionConfig.objects.filter(code=self.region_code)
                    .only("default_language")
                    .first()
                )
                if region and region.default_language:
                    return region.default_language
            except (
                ObjectDoesNotExist,
                DatabaseError,
                TypeError,
                ValueError,
                AttributeError,
            ):
                log_exception_with_context(
                    "reports.ReportCard.get_language: region default_language lookup failed",
                    school_id=getattr(self.student, "school_id", None)
                    if getattr(self, "student", None)
                    else None,
                    extra={
                        "region_code": self.region_code,
                        "report_card_id": getattr(self, "id", None),
                    },
                )
        return "en"

    def get_region(self):
        """Get region for this report card."""
        from apps.global_registries.models import RegionConfig

        if self.region_code:
            try:
                return RegionConfig.objects.get(code=self.region_code)
            except RegionConfig.DoesNotExist:
                pass

        # Placeholder: future school region mapping (student.current_classroom → region)
        return None


class ReportCardAudit(models.Model):
    report_card = models.ForeignKey(
        ReportCard, on_delete=models.CASCADE, related_name="audits"
    )
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_card_audits",
    )
    action = models.CharField(max_length=40)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.report_card} - {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class ReportDocumentHash(models.Model):
    """
    Immutable verification ledger entry for generated report PDFs.
    Stores the SHA-256 digest used by external verifiers.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="report_document_hashes",
        null=True,
        blank=True,
    )
    report_card = models.OneToOneField(
        ReportCard,
        on_delete=models.CASCADE,
        related_name="document_hash",
    )
    sha256_hash = models.CharField(max_length=64, db_index=True)
    file_size_bytes = models.PositiveIntegerField(default=0)
    on_chain_status = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        help_text="e.g. anchored, pending, revoked; set when credential is verified on-chain",
    )
    blockchain_tx_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Transaction ID or proof identifier from blockchain gateway",
    )
    generated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="generated_report_hashes",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["sha256_hash", "created_at"],
                name="reports_rep_sha256_9bb6cb_idx",
            ),
            models.Index(
                fields=["school", "created_at"], name="reports_rep_school__6d1cfb_idx"
            ),
        ]

    def __str__(self):
        return f"Report hash {self.sha256_hash[:12]}... ({self.report_card_id})"


class PromotionRule(models.Model):
    """Promotion thresholds per academic year with optional classroom overrides."""

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="promotion_rules"
    )
    classroom = models.ForeignKey(
        Classroom,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="promotion_rules",
    )
    promotion_average = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    demotion_average = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    use_technical_promotion_rule = models.BooleanField(
        default=False,
        help_text="When enabled, use ITC/ATC rule: pass in at least 5 subjects including at least 2 Professional and 1 Related (in addition to overall average).",
    )

    class Meta:
        unique_together = ("academic_year", "classroom")

    def clean(self):
        if self.demotion_average > self.promotion_average:
            raise ValidationError(
                "Demotion average cannot be higher than promotion average."
            )

    def __str__(self):
        scope = self.classroom.name if self.classroom else "School default"
        return f"{self.academic_year} - {scope}"


class EMISSubmission(models.Model):
    """
    Government/District EMIS: track report preparation and submission per school/period.
    Platform 5Y: full ministry reporting and submission flow.
    """

    class ReportType(models.TextChoices):
        ENROLLMENT = "ENROLLMENT", "Enrollment"
        ATTENDANCE = "ATTENDANCE", "Attendance"
        FINANCE = "FINANCE", "Finance"
        STAFF = "STAFF", "Staff"
        MOE_PRESET = "MOE_PRESET", "MoE preset (regulatory)"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PREPARED = "PREPARED", "Prepared"
        SUBMITTED = "SUBMITTED", "Submitted"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        FAILED = "FAILED", "Failed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="emis_submissions",
    )
    report_type = models.CharField(
        max_length=32, choices=ReportType.choices, db_index=True
    )
    period_label = models.CharField(
        max_length=80,
        help_text="e.g. 2024-Q1, 2024/2025 Term 1",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emis_submissions",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emis_submissions",
    )
    preset_id = models.CharField(
        max_length=80, blank=True, help_text="MoE preset id when report_type=MOE_PRESET"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    file_path = models.CharField(
        max_length=500, blank=True, help_text="Generated report file (PDF/CSV)"
    )
    submission_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Ministry/district submission URL if applicable",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emis_submissions",
    )
    external_id = models.CharField(
        max_length=120, blank=True, help_text="Reference from ministry/district"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "report_type", "period_label"]),
            models.Index(fields=["school", "status"]),
        ]
        verbose_name = "EMIS submission"
        verbose_name_plural = "EMIS submissions"

    def __str__(self):
        return f"{self.school.name} — {self.report_type} {self.period_label} ({self.status})"


class ReportPack(models.Model):
    """
    Phase 10 — 10.3: Report library. Pack of report definitions; preview with seeded sample data; dependency mapping.
    """

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    dependency_schema = models.JSONField(
        default=dict, blank=True, help_text="Fields, policies, templates dependencies."
    )
    sample_data_config = models.JSONField(
        default=dict, blank=True, help_text="Seeded sample data for preview."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "reports"
        verbose_name = "Report Pack"
        verbose_name_plural = "Report Packs"
        ordering = ["code"]

    def __str__(self):
        return self.name or self.code


class TenantReportSchedule(models.Model):
    """
    Tenant-scoped scheduled report delivery (replaces BI ScheduledReport after reports.0017).
    Processed by ``send_scheduled_reports``; listed under ``reports_scheduled_delivery`` gates.
    """

    class Frequency(models.TextChoices):
        DAILY = "DAILY", "Daily"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"
        QUARTERLY = "QUARTERLY", "Quarterly"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="report_schedules",
    )
    name = models.CharField(max_length=255)
    report_key = models.SlugField(
        max_length=80,
        default="summary",
        help_text="Stable key for report type / template wiring.",
    )
    schedule_frequency = models.CharField(max_length=20, choices=Frequency.choices)
    schedule_time = models.TimeField()
    recipients = models.JSONField(default=list, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tenant_report_schedules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_run"]
        indexes = [
            models.Index(fields=["school", "is_active", "next_run"]),
        ]

    def clean(self):
        super().clean()
        if self.is_active:
            r = self.recipients
            if not isinstance(r, list) or len(r) == 0:
                raise ValidationError(
                    {
                        "recipients": "Active schedules need at least one recipient email.",
                    }
                )

    def __str__(self):
        return f"{self.school_id}:{self.name}"


class AdHocReportDefinition(models.Model):
    """
    Tenant-scoped ad-hoc report definition used by the ad-hoc runner.
    """

    ENTITY_TYPES = [
        ("STUDENTS", "Students"),
        ("ATTENDANCE", "Attendance"),
        ("FINANCE", "Finance (invoices/payments)"),
        ("ENROLLMENT", "Enrollment"),
        ("CUSTOM", "Custom"),
    ]
    OUTPUT_FORMATS = [
        ("CSV", "CSV"),
        ("JSON", "JSON"),
    ]

    name = models.CharField(max_length=255)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="adhoc_report_definitions",
        null=True,
        blank=True,
        help_text="Tenant scope; null for global.",
    )
    entity_type = models.CharField(
        max_length=32, choices=ENTITY_TYPES, default="STUDENTS"
    )
    columns = models.JSONField(
        default=list,
        help_text='List of column keys to output, e.g. ["id", "first_name", "last_name", "classroom__name"].',
    )
    filters = models.JSONField(
        default=dict,
        help_text='Filters: {"classroom_id": 1, "is_active": true} or {"date_from": "2024-01-01", "date_to": "2024-12-31"}.',
    )
    date_from = models.DateField(
        null=True, blank=True, help_text="Override or default date range start."
    )
    date_to = models.DateField(
        null=True, blank=True, help_text="Override or default date range end."
    )
    output_format = models.CharField(
        max_length=10, choices=OUTPUT_FORMATS, default="CSV"
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="adhoc_report_definitions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["school", "entity_type"], name="reports_adh_school__0b5d4d_idx"
            ),
            models.Index(
                fields=["school", "is_active"], name="reports_adh_school__d73152_idx"
            ),
        ]
        verbose_name = "Ad-hoc report definition"
        verbose_name_plural = "Ad-hoc report definitions"

    def __str__(self):
        return f"{self.name} ({self.entity_type})"


class AdHocReportExecution(models.Model):
    """Track ad-hoc report run history."""

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    definition = models.ForeignKey(
        AdHocReportDefinition, on_delete=models.CASCADE, related_name="executions"
    )
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    parameters_override = models.JSONField(
        default=dict, help_text="Optional override for date_from/date_to or filters."
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    row_count = models.IntegerField(null=True, blank=True)
    file_path = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)
    execution_time_ms = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["definition", "created_at"],
                name="reports_adh_definit_ebc5fb_idx",
            )
        ]

    def __str__(self):
        return f"{self.definition.name} - {self.status} @ {self.created_at}"


# ReportDefinition and MaterializedReportCache are intentionally not registered here.
# reports.0017 retired those BI tables. apps.reports.bi_models keeps
# compatibility aliases for the live ad-hoc report models.
