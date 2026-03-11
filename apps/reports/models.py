from django.db import models
from apps.academics.models import AcademicYear, Term, Classroom
from apps.people.models import StudentProfile
from apps.accounts.models import User
from django.core.exceptions import ValidationError
from django.utils import translation


def reportcard_pdf_upload_to(instance, filename):
    """Tenant-scoped path for ReportCard.pdf_file (Section 25.3, media_tenant_scope.md)."""
    school_id = getattr(instance, "school_id", None) or (
        getattr(getattr(instance, "school", None), "pk", None) if getattr(instance, "school", None) else None
    )
    if school_id is None:
        return f"tenant_uploads/reports/reportcards/{filename}"
    return f"tenants/{school_id}/reports/reportcards/{filename}"


class TermPublishStatus(models.Model):
    """
    If classroom is NULL, it means published for the entire school for that term.
    If classroom is set, publish applies only to that class.
    """
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="publish_statuses")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="publish_statuses")
    classroom = models.ForeignKey(Classroom, null=True, blank=True, on_delete=models.CASCADE, related_name="publish_statuses")

    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="publishes")

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
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="report_cards")
    term = models.ForeignKey(Term, null=True, blank=True, on_delete=models.CASCADE, related_name="report_cards")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="report_cards")

    type = models.CharField(max_length=10, choices=Type.choices)
    pdf_file = models.FileField(upload_to=reportcard_pdf_upload_to, null=True, blank=True)
    generated_at = models.DateTimeField(auto_now=True)
    
    # Localization fields
    language = models.CharField(max_length=10, default='en', help_text='Language for certificate generation')
    region_code = models.CharField(max_length=10, null=True, blank=True, help_text='Region code for score conversion')

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

                region = RegionConfig.objects.filter(code=self.region_code).only("default_language").first()
                if region and region.default_language:
                    return region.default_language
            except Exception:
                pass
        return 'en'
    
    def get_region(self):
        """Get region for this report card."""
        from apps.global_registries.models import RegionConfig
        
        if self.region_code:
            try:
                return RegionConfig.objects.get(code=self.region_code)
            except RegionConfig.DoesNotExist:
                pass
        
        # Try to get from student's school (would need school region mapping)
        if self.student and self.student.current_classroom:
            try:
                # Placeholder for future school region mapping
                pass
            except Exception:
                pass
        return None


class ReportCardAudit(models.Model):
    report_card = models.ForeignKey(ReportCard, on_delete=models.CASCADE, related_name="audits")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="report_card_audits")
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
            models.Index(fields=["sha256_hash", "created_at"], name="reports_rep_sha256_9bb6cb_idx"),
            models.Index(fields=["school", "created_at"], name="reports_rep_school__6d1cfb_idx"),
        ]

    def __str__(self):
        return f"Report hash {self.sha256_hash[:12]}... ({self.report_card_id})"


class PromotionRule(models.Model):
    """Promotion thresholds per academic year with optional classroom overrides."""
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="promotion_rules")
    classroom = models.ForeignKey(Classroom, null=True, blank=True, on_delete=models.CASCADE, related_name="promotion_rules")
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
            raise ValidationError("Demotion average cannot be higher than promotion average.")

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
    report_type = models.CharField(max_length=32, choices=ReportType.choices, db_index=True)
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
    preset_id = models.CharField(max_length=80, blank=True, help_text="MoE preset id when report_type=MOE_PRESET")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    file_path = models.CharField(max_length=500, blank=True, help_text="Generated report file (PDF/CSV)")
    submission_url = models.URLField(max_length=500, blank=True, help_text="Ministry/district submission URL if applicable")
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emis_submissions",
    )
    external_id = models.CharField(max_length=120, blank=True, help_text="Reference from ministry/district")
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
    dependency_schema = models.JSONField(default=dict, blank=True, help_text="Fields, policies, templates dependencies.")
    sample_data_config = models.JSONField(default=dict, blank=True, help_text="Seeded sample data for preview.")
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


# ReportDefinition and MaterializedReportCache are defined in `apps.reports.bi_models`.
# Import them here for backwards compatibility so existing imports continue to work.
from .bi_models import ReportDefinition, MaterializedReportCache
