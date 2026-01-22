"""
Compliance models for regional legal requirements and document management.
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.siteconfig.models import RegionConfig
from django.conf import settings
from django.contrib.auth.models import User


class ComplianceRule(models.Model):
    """
    Base compliance rule template that can be applied to regions.
    Defines standard requirements like data retention, certificate format, etc.
    """
    RULE_TYPES = [
        ('data_retention', 'Data Retention'),
        ('certificate_format', 'Certificate Format'),
        ('student_id_format', 'Student ID Format'),
        ('document_validation', 'Document Validation'),
        ('privacy_policy', 'Privacy Policy'),
        ('terms_of_service', 'Terms of Service'),
        ('data_agreement', 'Data Processing Agreement'),
    ]

    name = models.CharField(max_length=200, unique=True)
    rule_type = models.CharField(max_length=50, choices=RULE_TYPES)
    description = models.TextField()
    
    # Rule parameters (JSON-like validation)
    applies_globally = models.BooleanField(default=False, help_text="If True, applies to all regions")
    is_mandatory = models.BooleanField(default=True, help_text="Must be enforced")
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_rules')
    
    class Meta:
        ordering = ['rule_type', 'name']
        verbose_name = 'Compliance Rule'
        verbose_name_plural = 'Compliance Rules'
    
    def __str__(self):
        return f"{self.get_rule_type_display()}: {self.name}"


class RegionalComplianceRequirement(models.Model):
    """
    Maps compliance rules to specific regions with customization.
    Handles regional variations in rules.
    """
    COMPLIANCE_STATUS = [
        ('pending', 'Pending'),
        ('implemented', 'Implemented'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    region = models.ForeignKey(RegionConfig, on_delete=models.CASCADE, related_name='compliance_requirements')
    rule = models.ForeignKey(ComplianceRule, on_delete=models.CASCADE, related_name='regional_requirements')
    
    # Regional customization
    description_override = models.TextField(
        blank=True,
        help_text="Override default rule description for this region"
    )
    custom_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Region-specific parameters (e.g., data retention months, ID format pattern)"
    )
    
    # Status tracking
    status = models.CharField(max_length=20, choices=COMPLIANCE_STATUS, default='pending')
    implementation_date = models.DateField(null=True, blank=True)
    enforcement_date = models.DateField(null=True, blank=True)
    
    # Deadline and notes
    deadline = models.DateField(null=True, blank=True, help_text="Compliance deadline for this region")
    notes = models.TextField(blank=True)
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_requirements')
    
    class Meta:
        unique_together = ('region', 'rule')
        ordering = ['region', 'rule__rule_type']
        verbose_name = 'Regional Compliance Requirement'
        verbose_name_plural = 'Regional Compliance Requirements'
    
    def __str__(self):
        return f"{self.region.code}: {self.rule.name}"
    
    def is_overdue(self):
        """Check if compliance deadline has passed."""
        if self.deadline and timezone.now().date() > self.deadline:
            return True
        return False


class ComplianceCheck(models.Model):
    """
    Records compliance verification checks performed on school operations.
    Tracks what was checked, when, and the result.
    """
    CHECK_STATUS = [
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('warning', 'Warning'),
        ('pending', 'Pending'),
    ]

    region = models.ForeignKey(RegionConfig, on_delete=models.CASCADE, related_name='compliance_checks')
    requirement = models.ForeignKey(RegionalComplianceRequirement, on_delete=models.CASCADE, related_name='checks')
    
    # Check details
    check_type = models.CharField(
        max_length=50,
        choices=[
            ('data_validation', 'Data Validation'),
            ('document_audit', 'Document Audit'),
            ('format_validation', 'Format Validation'),
            ('policy_review', 'Policy Review'),
            ('scheduled_review', 'Scheduled Review'),
        ],
        default='scheduled_review'
    )
    status = models.CharField(max_length=20, choices=CHECK_STATUS)
    
    # Results
    findings = models.TextField(help_text="Detailed findings from the compliance check")
    issues_found = models.IntegerField(default=0, help_text="Number of compliance issues found")
    issues_resolved = models.IntegerField(default=0, help_text="Number of issues already resolved")
    
    # Timestamps
    check_date = models.DateTimeField(auto_now_add=True)
    next_check_date = models.DateField(null=True, blank=True)
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='compliance_checks')
    
    # Remediation
    remediation_required = models.BooleanField(default=False)
    remediation_deadline = models.DateField(null=True, blank=True)
    remediation_notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-check_date']
        verbose_name = 'Compliance Check'
        verbose_name_plural = 'Compliance Checks'
    
    def __str__(self):
        return f"{self.region.code} - {self.get_check_type_display()} ({self.get_status_display()})"


class LegalDocument(models.Model):
    """
    Manages legal documents (privacy policy, terms of service, data agreements).
    Tracks versions and language variants.
    """
    DOCUMENT_TYPES = [
        ('privacy_policy', 'Privacy Policy'),
        ('terms_of_service', 'Terms of Service'),
        ('data_agreement', 'Data Processing Agreement'),
        ('parental_consent', 'Parental Consent Form'),
        ('user_agreement', 'User Agreement'),
    ]

    LANGUAGES = [
        ('en', 'English'),
        ('fr', 'French'),
        ('sw', 'Swahili'),
        ('yo', 'Yoruba'),
        ('pid', 'Pidgin'),
        ('ha', 'Hausa'),
    ]

    region = models.ForeignKey(RegionConfig, on_delete=models.CASCADE, related_name='legal_documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    language = models.CharField(max_length=10, choices=LANGUAGES, default='en')
    
    # Content
    title = models.CharField(max_length=300)
    content = models.TextField(help_text="Full HTML/text content of the legal document")
    version = models.IntegerField(default=1, help_text="Document version number")
    
    # Dates
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Audit
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_legal_documents')
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('region', 'document_type', 'language', 'version')
        ordering = ['region', 'document_type', 'language', '-version']
        verbose_name = 'Legal Document'
        verbose_name_plural = 'Legal Documents'
    
    def __str__(self):
        return f"{self.region.code} - {self.get_document_type_display()} ({self.language.upper()}) v{self.version}"
    
    def is_expired(self):
        """Check if document has expired."""
        if self.expiry_date and timezone.now().date() > self.expiry_date:
            return True
        return False


class ComplianceAuditLog(models.Model):
    """
    Comprehensive audit trail for compliance-related actions.
    Tracks who did what and when.
    """
    ACTION_TYPES = [
        ('check_performed', 'Compliance Check Performed'),
        ('requirement_created', 'Requirement Created'),
        ('requirement_updated', 'Requirement Updated'),
        ('document_created', 'Document Created'),
        ('document_updated', 'Document Updated'),
        ('document_accessed', 'Document Accessed'),
        ('policy_enforced', 'Policy Enforced'),
        ('remediation_assigned', 'Remediation Assigned'),
        ('remediation_completed', 'Remediation Completed'),
        ('escalation', 'Issue Escalated'),
    ]

    region = models.ForeignKey(RegionConfig, on_delete=models.CASCADE, related_name='audit_logs')
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    
    # What was affected
    requirement = models.ForeignKey(
        RegionalComplianceRequirement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    document = models.ForeignKey(
        LegalDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    
    # Details
    description = models.TextField(help_text="Details of the action performed")
    details = models.JSONField(default=dict, blank=True, help_text="Additional JSON data")
    
    # Who and when
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='compliance_audit_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Impact assessment
    severity = models.CharField(
        max_length=20,
        choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')],
        default='medium'
    )
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Compliance Audit Log'
        verbose_name_plural = 'Compliance Audit Logs'
        indexes = [
            models.Index(fields=['region', '-timestamp']),
            models.Index(fields=['action_type', '-timestamp']),
            models.Index(fields=['severity', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.region.code} - {self.get_action_type_display()} ({self.timestamp.date()})"


class StudentIDFormat(models.Model):
    """
    Defines student ID format requirements per region.
    Ensures compliance with regional ID standards.
    """
    region = models.OneToOneField(RegionConfig, on_delete=models.CASCADE, related_name='compliance_student_id_format')
    
    # Format pattern (e.g., "CMR-YY-nnnn" where YY=year, nnnn=sequential)
    format_pattern = models.CharField(
        max_length=100,
        help_text="Pattern: region prefix, YY (year), nnn (sequential), other identifiers"
    )
    prefix = models.CharField(max_length=5, help_text="Regional prefix for student IDs")
    
    # Validation rules
    min_length = models.IntegerField(default=10, validators=[MinValueValidator(5)])
    max_length = models.IntegerField(default=20, validators=[MaxValueValidator(50)])
    allow_letters = models.BooleanField(default=True)
    allow_numbers = models.BooleanField(default=True)
    allow_special_chars = models.BooleanField(default=False)
    
    # Example
    example_id = models.CharField(max_length=100, help_text="Example of valid ID format")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Student ID Format'
        verbose_name_plural = 'Student ID Formats'
    
    def __str__(self):
        return f"{self.region.name} - {self.format_pattern}"


class CertificateTemplate(models.Model):
    """
    Regional certificate templates with compliance requirements.
    """
    region = models.ForeignKey(RegionConfig, on_delete=models.CASCADE, related_name='certificate_templates')
    
    # Template details
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Format specifications
    paper_size = models.CharField(
        max_length=50,
        choices=[('A4', 'A4'), ('letter', 'Letter'), ('A3', 'A3')],
        default='A4'
    )
    orientation = models.CharField(
        max_length=20,
        choices=[('portrait', 'Portrait'), ('landscape', 'Landscape')],
        default='landscape'
    )
    
    # Compliance fields that must be included
    requires_school_seal = models.BooleanField(default=True)
    requires_principal_signature = models.BooleanField(default=True)
    requires_official_stamp = models.BooleanField(default=True)
    requires_issue_date = models.BooleanField(default=True)
    requires_validity_date = models.BooleanField(default=False)
    
    # Content
    template_html = models.TextField(help_text="HTML template with placeholders")
    css_styling = models.TextField(blank=True, help_text="CSS for styling")
    
    # Versioning
    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('region', 'name', 'version')
        ordering = ['region', 'name', '-version']
        verbose_name = 'Certificate Template'
        verbose_name_plural = 'Certificate Templates'
    
    def __str__(self):
        return f"{self.region.name} - {self.name} (v{self.version})"
