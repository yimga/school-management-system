from __future__ import annotations

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
import uuid
import os

from apps.accounts.validators import validate_document_file, validate_file_size_10mb


class PortalFeatureItem(models.Model):
    class Feature(models.TextChoices):
        MESSAGING = "messaging", "Messaging"
        FORUMS = "forums", "Forums"
        VIDEO = "video", "Video"
        DOCUMENTS = "documents", "Documents"
        SYLLABUS = "syllabus", "Syllabus"

    class DocumentType(models.TextChoices):
        GENERAL = "GENERAL", "General Document"
        FORM = "FORM", "Form (Requires Signature)"
        POLICY = "POLICY", "Policy Document"
        HANDBOOK = "HANDBOOK", "Handbook"
        TIMETABLE = "TIMETABLE", "Timetable"
        ANNOUNCEMENT = "ANNOUNCEMENT", "Announcement"
        OTHER = "OTHER", "Other"

    feature = models.CharField(max_length=20, choices=Feature.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    link = models.URLField(blank=True, help_text="External link (if document is hosted elsewhere)")
    # File upload support
    file = models.FileField(
        upload_to="portal/documents/%Y/%m/",
        blank=True,
        null=True,
        validators=[validate_document_file, validate_file_size_10mb],
        help_text="Upload a document file (PDF, Word, Excel) - max 10MB"
    )
    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.GENERAL,
        help_text="Type of document (forms require signature)"
    )
    requires_signature = models.BooleanField(
        default=False,
        help_text="If checked, this form requires electronic signature from parents/students"
    )
    is_active = models.BooleanField(default=True)
    # Access control
    visible_to_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="List of roles that can see this document (empty = all authenticated users)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="portal_feature_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Portal Feature Item"
        verbose_name_plural = "Portal Feature Items"
        indexes = [
            models.Index(fields=["feature", "is_active"]),
            models.Index(fields=["document_type", "requires_signature"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_feature_display()}: {self.title}"

    def clean(self):
        """Validate that either link or file is provided"""
        if not self.link and not self.file:
            raise ValidationError("Either a link or file must be provided.")
        if self.link and self.file:
            raise ValidationError("Provide either a link OR a file, not both.")

    @property
    def has_file(self) -> bool:
        """Check if document has an uploaded file"""
        return bool(self.file)

    @property
    def file_size_mb(self) -> float:
        """Get file size in MB"""
        if self.file:
            return round(self.file.size / (1024 * 1024), 2)
        return 0.0

    @property
    def file_extension(self) -> str:
        """Get file extension"""
        if self.file:
            return os.path.splitext(self.file.name)[1].lower()
        return ""

    def can_view(self, user) -> bool:
        """Check if user can view this document"""
        if not self.is_active:
            return False
        if not user.is_authenticated:
            return False
        # If no role restrictions, all authenticated users can view
        if not self.visible_to_roles:
            return True
        # Check if user's role is in allowed roles
        user_role = getattr(user, "role", None)
        if user_role:
            return str(user_role) in self.visible_to_roles
        # Staff/superuser can always view
        return user.is_staff or user.is_superuser


class PendingGuardianInvite(models.Model):
    """
    A lightweight invite that lets staff issue a claim token to a parent/guardian.
    The parent claims it from the portal and we create the StudentGuardian link.
    """

    class Relationship(models.TextChoices):
        MOTHER = "MOTHER", "Mother"
        FATHER = "FATHER", "Father"
        GUARDIAN = "GUARDIAN", "Guardian"
        OTHER = "OTHER", "Other"

    class PreferredContact(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        PHONE = "PHONE", "Phone Call"

    token = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey("people.StudentProfile", on_delete=models.CASCADE, related_name="pending_invites")
    invited_email = models.EmailField(blank=True)
    invited_phone = models.CharField(max_length=50, blank=True)
    relationship = models.CharField(
        max_length=20, choices=Relationship.choices, default=Relationship.GUARDIAN
    )
    preferred_contact = models.CharField(
        max_length=20, choices=PreferredContact.choices, default=PreferredContact.EMAIL
    )
    referral_code = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="guardian_invites"
    )
    guardian_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="claimed_invites"
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invite {self.student} -> {self.invited_email or self.invited_phone or self.token}"

    @property
    def is_claimed(self) -> bool:
        return bool(self.claimed_at and self.guardian_user)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4().hex
        super().save(*args, **kwargs)


class Announcement(models.Model):
    """
    Global announcement banner that can be displayed on all pages.
    Admins can control announcements with different types and colors.
    """
    
    class BannerType(models.TextChoices):
        INFO = "info", "Information (Blue)"
        SUCCESS = "success", "Success (Green)"
        WARNING = "warning", "Warning (Yellow)"
        DANGER = "danger", "Danger (Red)"
    
    title = models.CharField(max_length=200, help_text="Announcement title (short)")
    message = models.TextField(help_text="Detailed announcement message")
    banner_type = models.CharField(
        max_length=20,
        choices=BannerType.choices,
        default=BannerType.INFO,
        help_text="Choose the banner color/type"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Display this announcement on all pages"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_announcements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to start showing this announcement (leave blank for immediate)"
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to stop showing this announcement (leave blank for indefinite)"
    )
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"
    
    def __str__(self) -> str:
        return f"{self.title} ({self.get_banner_type_display()})"
    
    @property
    def is_currently_active(self) -> bool:
        """Check if announcement should be displayed based on date range"""
        from django.utils import timezone
        now = timezone.now()
        
        if not self.is_active:
            return False
        
        if self.start_date and now < self.start_date:
            return False
        
        if self.end_date and now > self.end_date:
            return False
        
        return True


class FormSignature(models.Model):
    """
    Electronic signature for school forms (registration, consent, extra fees, etc.)
    Tracks who signed what form and when.
    """
    
    class SignatureStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Signature"
        SIGNED = "SIGNED", "Signed"
        REJECTED = "REJECTED", "Rejected"
        EXPIRED = "EXPIRED", "Expired"

    # Link to the form document
    form_document = models.ForeignKey(
        PortalFeatureItem,
        on_delete=models.CASCADE,
        related_name="signatures",
        limit_choices_to={"requires_signature": True, "document_type": "FORM"},
        help_text="The form that requires signature"
    )
    
    # Who needs to sign
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="form_signatures",
        null=True,
        blank=True,
        help_text="Student this form is for (if applicable)"
    )
    
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signed_forms",
        limit_choices_to={"role": "PARENT"},
        null=True,
        blank=True,
        help_text="Parent/guardian signing the form"
    )
    
    # Signature details
    status = models.CharField(
        max_length=20,
        choices=SignatureStatus.choices,
        default=SignatureStatus.PENDING
    )
    
    signed_at = models.DateTimeField(null=True, blank=True)
    signature_ip = models.GenericIPAddressField(null=True, blank=True)
    signature_user_agent = models.CharField(max_length=500, blank=True)
    
    # Signature data (stored securely)
    signature_data = models.TextField(
        blank=True,
        help_text="Base64-encoded signature image or signature hash"
    )
    signature_hash = models.CharField(
        max_length=256,
        blank=True,
        help_text="SHA-256 hash of signature for verification"
    )
    
    # Additional data
    signed_pdf = models.FileField(
        upload_to="portal/signed_forms/%Y/%m/",
        blank=True,
        null=True,
        help_text="Final signed PDF document"
    )
    
    notes = models.TextField(
        blank=True,
        help_text="Any additional notes or comments"
    )
    
    # Expiry and reminders
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this signature request expires"
    )
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Audit trail
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_signature_requests",
        help_text="Admin who created this signature request"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Form Signature"
        verbose_name_plural = "Form Signatures"
        indexes = [
            models.Index(fields=["form_document", "status"]),
            models.Index(fields=["student", "status"]),
            models.Index(fields=["parent", "status"]),
            models.Index(fields=["expires_at", "status"]),
        ]
        unique_together = [
            ("form_document", "student", "parent"),
        ]

    def __str__(self) -> str:
        signer = self.parent.get_full_name() if self.parent else "Unknown"
        student = self.student.admission_number if self.student else "N/A"
        return f"{self.form_document.title} - {signer} (Student: {student})"

    @property
    def is_expired(self) -> bool:
        """Check if signature request has expired"""
        from django.utils import timezone
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    @property
    def can_sign(self) -> bool:
        """Check if form can still be signed"""
        return (
            self.status == FormSignature.SignatureStatus.PENDING
            and not self.is_expired
        )

    def mark_as_signed(self, signature_data: str, signature_hash: str, request=None):
        """Mark form as signed with signature data"""
        from django.utils import timezone
        
        self.status = FormSignature.SignatureStatus.SIGNED
        self.signed_at = timezone.now()
        self.signature_data = signature_data
        self.signature_hash = signature_hash
        
        if request:
            self.signature_ip = self._get_client_ip(request)
            self.signature_user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        
        self.save()

    def _get_client_ip(self, request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

