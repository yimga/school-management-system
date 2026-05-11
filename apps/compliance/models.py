"""
Compliance & Legal Framework models for regional requirements and document management.
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.global_registries.models import RegionConfig
from django.conf import settings


class ComplianceRule(models.Model):
    """Base compliance rule template that can be applied to regions."""

    RULE_TYPES = [
        ("data_retention", "Data Retention"),
        ("certificate_format", "Certificate Format"),
        ("student_id_format", "Student ID Format"),
        ("document_validation", "Document Validation"),
        ("privacy_policy", "Privacy Policy"),
        ("terms_of_service", "Terms of Service"),
        ("data_agreement", "Data Processing Agreement"),
    ]

    name = models.CharField(max_length=200, unique=True)
    rule_type = models.CharField(max_length=50, choices=RULE_TYPES)
    description = models.TextField()
    applies_globally = models.BooleanField(default=False)
    is_mandatory = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_rules",
    )

    class Meta:
        ordering = ["rule_type", "name"]
        verbose_name = "Compliance Rule"
        verbose_name_plural = "Compliance Rules"

    def __str__(self):
        return f"{self.get_rule_type_display()}: {self.name}"


class RegionalComplianceRequirement(models.Model):
    """Maps compliance rules to specific regions with customization."""

    COMPLIANCE_STATUS = [
        ("pending", "Pending"),
        ("implemented", "Implemented"),
        ("active", "Active"),
        ("archived", "Archived"),
    ]

    region = models.ForeignKey(
        RegionConfig, on_delete=models.CASCADE, related_name="compliance_requirements"
    )
    rule = models.ForeignKey(
        ComplianceRule, on_delete=models.CASCADE, related_name="regional_requirements"
    )
    description_override = models.TextField(blank=True)
    custom_parameters = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, choices=COMPLIANCE_STATUS, default="pending"
    )
    implementation_date = models.DateField(null=True, blank=True)
    enforcement_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_requirements",
    )

    class Meta:
        unique_together = ("region", "rule")
        ordering = ["region", "rule__rule_type"]

    def __str__(self):
        return f"{self.region.code}: {self.rule.name}"

    def is_overdue(self):
        if self.deadline and timezone.now().date() > self.deadline:
            return True
        return False


class ComplianceCheck(models.Model):
    """Records compliance verification checks performed."""

    CHECK_STATUS = [
        ("pass", "Pass"),
        ("fail", "Fail"),
        ("warning", "Warning"),
        ("pending", "Pending"),
    ]

    region = models.ForeignKey(
        RegionConfig, on_delete=models.CASCADE, related_name="compliance_checks"
    )
    requirement = models.ForeignKey(
        RegionalComplianceRequirement, on_delete=models.CASCADE, related_name="checks"
    )
    check_type = models.CharField(
        max_length=50,
        choices=[
            ("data_validation", "Data Validation"),
            ("document_audit", "Document Audit"),
            ("format_validation", "Format Validation"),
            ("policy_review", "Policy Review"),
            ("scheduled_review", "Scheduled Review"),
        ],
        default="scheduled_review",
    )
    status = models.CharField(max_length=20, choices=CHECK_STATUS)
    findings = models.TextField()
    issues_found = models.IntegerField(default=0)
    issues_resolved = models.IntegerField(default=0)
    check_date = models.DateTimeField(auto_now_add=True)
    next_check_date = models.DateField(null=True, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="compliance_checks",
    )
    remediation_required = models.BooleanField(default=False)
    remediation_deadline = models.DateField(null=True, blank=True)
    remediation_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-check_date"]
        verbose_name = "Compliance Check"
        verbose_name_plural = "Compliance Checks"

    def __str__(self):
        return f"{self.region.code} - {self.get_check_type_display()} ({self.get_status_display()})"


class LegalDocument(models.Model):
    """Manages legal documents in multiple languages."""

    DOCUMENT_TYPES = [
        ("privacy_policy", "Privacy Policy"),
        ("terms_of_service", "Terms of Service"),
        ("data_agreement", "Data Processing Agreement"),
        ("parental_consent", "Parental Consent Form"),
        ("user_agreement", "User Agreement"),
    ]

    LANGUAGES = [
        ("en", "English"),
        ("fr", "French"),
        ("sw", "Swahili"),
        ("yo", "Yoruba"),
        ("pid", "Pidgin"),
        ("ha", "Hausa"),
    ]

    region = models.ForeignKey(
        RegionConfig, on_delete=models.CASCADE, related_name="legal_documents"
    )
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    language = models.CharField(max_length=10, choices=LANGUAGES, default="en")
    title = models.CharField(max_length=300)
    content = models.TextField()
    version = models.IntegerField(default=1)
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_legal_documents",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("region", "document_type", "language", "version")
        ordering = ["region", "document_type", "language", "-version"]

    def __str__(self):
        return f"{self.region.code} - {self.get_document_type_display()} ({self.language.upper()}) v{self.version}"

    def is_expired(self):
        if self.expiry_date and timezone.now().date() > self.expiry_date:
            return True
        return False


class ComplianceAuditLog(models.Model):
    """Audit trail for compliance-related actions."""

    ACTION_TYPES = [
        ("check_performed", "Compliance Check Performed"),
        ("requirement_created", "Requirement Created"),
        ("requirement_updated", "Requirement Updated"),
        ("document_created", "Document Created"),
        ("document_updated", "Document Updated"),
        ("document_accessed", "Document Accessed"),
        ("policy_enforced", "Policy Enforced"),
        ("remediation_assigned", "Remediation Assigned"),
        ("remediation_completed", "Remediation Completed"),
        ("escalation", "Issue Escalated"),
    ]

    region = models.ForeignKey(
        RegionConfig, on_delete=models.CASCADE, related_name="audit_logs"
    )
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    requirement = models.ForeignKey(
        RegionalComplianceRequirement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    description = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="compliance_audit_logs",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    severity = models.CharField(
        max_length=20,
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
        default="medium",
    )

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Compliance Audit Log"
        verbose_name_plural = "Compliance Audit Logs"
        indexes = [
            models.Index(fields=["region", "-timestamp"]),
            models.Index(fields=["action_type", "-timestamp"]),
            models.Index(fields=["severity", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.region.code} - {self.get_action_type_display()} ({self.timestamp.date()})"


class StudentIDFormat(models.Model):
    """Student ID format requirements per region."""

    region = models.OneToOneField(
        RegionConfig,
        on_delete=models.CASCADE,
        related_name="compliance_student_id_format",
    )
    format_pattern = models.CharField(max_length=100)
    prefix = models.CharField(max_length=5)
    min_length = models.IntegerField(default=10, validators=[MinValueValidator(5)])
    max_length = models.IntegerField(default=20, validators=[MaxValueValidator(50)])
    allow_letters = models.BooleanField(default=True)
    allow_numbers = models.BooleanField(default=True)
    allow_special_chars = models.BooleanField(default=False)
    example_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student ID Format"
        verbose_name_plural = "Student ID Formats"

    def __str__(self):
        return f"{self.region.name} - {self.format_pattern}"


class CertificateTemplate(models.Model):
    """Regional certificate templates with compliance requirements."""

    region = models.ForeignKey(
        RegionConfig, on_delete=models.CASCADE, related_name="certificate_templates"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    paper_size = models.CharField(
        max_length=50,
        choices=[("A4", "A4"), ("letter", "Letter"), ("A3", "A3")],
        default="A4",
    )
    orientation = models.CharField(
        max_length=20,
        choices=[("portrait", "Portrait"), ("landscape", "Landscape")],
        default="landscape",
    )
    requires_school_seal = models.BooleanField(default=True)
    requires_principal_signature = models.BooleanField(default=True)
    requires_official_stamp = models.BooleanField(default=True)
    requires_issue_date = models.BooleanField(default=True)
    requires_validity_date = models.BooleanField(default=False)
    template_html = models.TextField()
    css_styling = models.TextField(blank=True)
    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("region", "name", "version")
        ordering = ["region", "name", "-version"]
        verbose_name = "Certificate Template"
        verbose_name_plural = "Certificate Templates"

    def __str__(self):
        return f"{self.region.name} - {self.name} (v{self.version})"


# ============================================
# Parental Permission & Consent Hub (plan 3.18)
# ============================================


class ConsentRequest(models.Model):
    """
    School-created consent event (e.g. field trip, photo usage, privacy policy).
    When document is updated, mark prior consents outdated and trigger new request.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="consent_requests",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=80,
        blank=True,
        help_text="e.g. field_trip, photo_usage, privacy_policy",
    )
    document_type = models.CharField(max_length=50, blank=True)
    document_version_id = models.IntegerField(
        null=True, blank=True, help_text="LegalDocument version or template version"
    )
    document_text = models.TextField(
        blank=True, help_text="Snapshot of text at creation for hash"
    )
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "is_active"])]

    def __str__(self):
        return f"{self.school.name}: {self.title}"


class ConsentRecord(models.Model):
    """
    Parent signature: SHA-256 hash of document at sign time; tenant-isolated.
    Withdrawal stores withdrawn_at and document version for audit.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="consent_records",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consent_records",
    )
    consent_request = models.ForeignKey(
        ConsentRequest,
        on_delete=models.CASCADE,
        related_name="records",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    document_hash = models.CharField(
        max_length=64, help_text="SHA-256 of document text at sign time"
    )
    signed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    document_version_at_sign = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-signed_at"]
        indexes = [
            models.Index(fields=["user", "school"]),
            models.Index(fields=["school", "signed_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} signed {self.title} @ {self.signed_at}"


# ============================================
# Phase Compliance (plan 3.9): Region → feature_code → status for guard
# ============================================


class RegionFeatureCompliance(models.Model):
    """
    Maps region to feature_code and status (ENABLED/DISABLED/RESTRICTED).
    Used by ComplianceGuardMiddleware to block restricted actions per region (e.g. EU GDPR).
    """

    class Status(models.TextChoices):
        ENABLED = "ENABLED", "Enabled"
        DISABLED = "DISABLED", "Disabled"
        RESTRICTED = "RESTRICTED", "Restricted (block with structured error)"

    region = models.ForeignKey(
        RegionConfig,
        on_delete=models.CASCADE,
        related_name="feature_compliance_rules",
    )
    feature_code = models.CharField(
        max_length=80,
        help_text="e.g. Right_to_Erasure, Export_All_Student_Data, COPPA_consent",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ENABLED,
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["region", "feature_code"]
        unique_together = [("region", "feature_code")]
        verbose_name = "Region feature compliance"
        verbose_name_plural = "Region feature compliance rules"

    def __str__(self):
        return f"{self.region.code}: {self.feature_code}={self.status}"


# ============================================
# Data governance: retention, export, erasure (RunMyCampus blueprint D)
# ============================================


class RetentionRule(models.Model):
    """
    Retention rule per data class / entity type (e.g. keep invoices 7 years).
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="retention_rules",
        null=True,
        blank=True,
    )
    data_class = models.CharField(
        max_length=80, help_text="e.g. invoice, consent_record, audit_log"
    )
    retention_days = models.PositiveIntegerField(
        help_text="Keep records this many days; then eligible for purge."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_class"]
        verbose_name = "Retention Rule"
        verbose_name_plural = "Retention Rules"

    def __str__(self):
        return f"{self.data_class}: {self.retention_days} days"


class ExportJob(models.Model):
    """Data export request (e.g. GDPR right to portability)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="export_jobs"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    scope = models.CharField(
        max_length=80, default="user", help_text="e.g. user, school"
    )
    scope_id = models.CharField(
        max_length=64, blank=True, help_text="e.g. user id for scope=user"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    file_path = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Pass 9.C: SLA tracking. GDPR Art. 12(3) sets one month; SOC 2 audits sample
    # against per-tenant due_at. breach_at is auto-populated when due_at passes
    # without completion (see compliance.tasks.mark_sla_breaches).
    due_at = models.DateTimeField(null=True, blank=True)
    sla_breach_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Export Job"
        verbose_name_plural = "Export Jobs"

    def __str__(self):
        return f"Export {self.id} ({self.status})"


class EraseRequest(models.Model):
    """Erasure request (e.g. GDPR right to be forgotten)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="erase_requests"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="erase_requests_as_subject",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Pass 9.C: SLA tracking. See ExportJob.due_at / sla_breach_at.
    due_at = models.DateTimeField(null=True, blank=True)
    sla_breach_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Erase Request"
        verbose_name_plural = "Erase Requests"

    def __str__(self):
        return f"Erase {self.subject_user_id} ({self.status})"


class FerpaDisclosure(models.Model):
    """
    Pass 9.B: FERPA §99.32 disclosure log. US K-12 schools must record every
    release of personally-identifiable student record information to anyone
    outside the school. Required fields: who released, what records, to whom,
    why, when, and whether parental consent (or a specific exception) applied.
    """

    class Purpose(models.TextChoices):
        CONSENT = "consent", "Parent or student consent"
        DIRECTORY = "directory_info", "Directory information release"
        SCHOOL_OFFICIAL = "school_official", "School official with legitimate interest"
        TRANSFER = "transfer", "Transfer to another school"
        AUDIT = "audit", "Audit / evaluation of education program"
        FINANCIAL_AID = "financial_aid", "Financial aid"
        ACCREDITATION = "accreditation", "Accreditation"
        JUDICIAL = "judicial_order", "Judicial order or subpoena"
        EMERGENCY = "health_safety", "Health or safety emergency"
        RESEARCH = "research", "Research approved by school"
        OTHER = "other", "Other (note required)"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="ferpa_disclosures",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="ferpa_disclosures",
    )
    disclosed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ferpa_disclosures_logged",
        help_text="School official who recorded this disclosure.",
    )
    recipient_name = models.CharField(
        max_length=255,
        help_text="Person who received the records (full name).",
    )
    recipient_org = models.CharField(
        max_length=255,
        blank=True,
        help_text="Organization or agency, when applicable.",
    )
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    parent_consent_obtained = models.BooleanField(
        default=False,
        help_text="True only when written consent is on file before disclosure.",
    )
    record_types_disclosed = models.JSONField(
        default=list,
        blank=True,
        help_text="List of record categories released (transcripts, attendance, disciplinary, …).",
    )
    disclosed_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-disclosed_at"]
        indexes = [
            models.Index(fields=["school", "-disclosed_at"]),
            models.Index(fields=["student", "-disclosed_at"]),
            models.Index(fields=["purpose"]),
        ]
        verbose_name = "FERPA Disclosure"
        verbose_name_plural = "FERPA Disclosures"

    def __str__(self):
        return f"FERPA disclosure {self.id} — student {self.student_id} → {self.recipient_name}"


# ============================================
# Phase 4: Audit & Monitoring Models
# ============================================
# Re-export AuditLog from models_audit for callers that import from .models (e.g. portal)
from apps.compliance.models_audit import AuditLog  # noqa: F401
