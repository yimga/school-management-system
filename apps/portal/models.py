from __future__ import annotations

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
import uuid
import os

from apps.accounts.validators import validate_document_file, validate_file_size_10mb


def _portal_upload_to(instance, filename, subpath, school_id):
    """Build tenant-prefixed path for portal uploads (Section 25.3). school_id from caller."""
    if school_id is None:
        return f"tenant_uploads/portal/{subpath}/{filename}"
    return f"tenants/{school_id}/portal/{subpath}/{filename}"


def _lesson_plan_upload_to(instance, filename):
    school_id = getattr(getattr(instance, "teacher", None), "school_id", None)
    return _portal_upload_to(instance, filename, "lesson_notes", school_id)


def _lesson_plan_attachment_upload_to(instance, filename):
    lp = getattr(instance, "lesson_plan", None)
    school_id = getattr(getattr(lp, "teacher", None), "school_id", None) if lp else None
    return _portal_upload_to(instance, filename, "lesson_notes/resources", school_id)


def _training_entry_upload_to(instance, filename):
    school_id = getattr(getattr(instance, "teacher", None), "school_id", None)
    return _portal_upload_to(instance, filename, "training", school_id)


def _justification_upload_to(instance, filename):
    school_id = getattr(getattr(instance, "student", None), "school_id", None)
    return _portal_upload_to(instance, filename, "justifications", school_id)


def _photo_upload_token_upload_to(instance, filename):
    school_id = getattr(getattr(instance, "student", None), "school_id", None) or getattr(
        getattr(instance, "teacher", None), "school_id", None
    )
    return _portal_upload_to(instance, filename, "photo_upload", school_id)


def _form_signature_upload_to(instance, filename):
    school_id = getattr(getattr(instance, "student", None), "school_id", None)
    return _portal_upload_to(instance, filename, "signed_forms", school_id)


def _portal_feature_item_file_upload_to(instance, filename):
    """Section 25.3: tenant-prefixed path for Document Library (PortalFeatureItem.file)."""
    school_id = getattr(instance, "school_id", None)
    return _portal_upload_to(instance, filename, "documents", school_id)


class DocumentCategory(models.Model):
    """Configurable folder/category for Document Library (e.g. Essential Student Records, Administrative, Pedagogical)."""
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    order = models.PositiveSmallIntegerField(default=0, help_text="Display order within same level.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Document category"
        verbose_name_plural = "Document categories"

    def __str__(self):
        return self.name


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
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="portal_feature_items",
        help_text="Tenant scope for document library (Section 25.3); set from request.school on save.",
    )
    # File upload support (Section 25.3: tenant-prefixed when school_id set)
    file = models.FileField(
        upload_to=_portal_feature_item_file_upload_to,
        blank=True,
        null=True,
        validators=[validate_document_file, validate_file_size_10mb],
        help_text="Upload a document (PDF, Word, Excel, or LibreOffice ODT/ODS) - max 10MB"
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
    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        help_text="Optional folder/category (Document Library structure).",
    )
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
        upload_to=_form_signature_upload_to,
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


class LessonPlan(models.Model):
    """Teacher weekly lesson notes (PDF upload). RBAC: teacher sees only their own."""
    teacher = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="lesson_plans",
    )
    title = models.CharField(max_length=200)
    week_start_date = models.DateField(help_text="Start of the teaching week")
    file = models.FileField(
        upload_to=_lesson_plan_upload_to,
        validators=[validate_document_file, validate_file_size_10mb],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-week_start_date", "-created_at"]
        verbose_name = "Lesson plan"
        verbose_name_plural = "Lesson plans"
        indexes = [models.Index(fields=["teacher", "-week_start_date"])]

    def __str__(self):
        return f"{self.title} – {self.week_start_date}"


class LessonPlanAttachment(models.Model):
    """Extra resource attachments for a lesson plan (Wave 6). One plan can have multiple files."""
    lesson_plan = models.ForeignKey(
        LessonPlan,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to=_lesson_plan_attachment_upload_to,
        validators=[validate_document_file, validate_file_size_10mb],
    )
    label = models.CharField(max_length=120, blank=True, help_text="Optional short label (e.g. Worksheet, Slides)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Lesson plan attachment"
        verbose_name_plural = "Lesson plan attachments"

    def __str__(self):
        return self.label or self.file.name


class CahierDeTexteEntry(models.Model):
    """Structured lesson diary entry (Cahier de Texte). Linked to syllabus; supervisor visa workflow."""
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        VISED = "VISED", "Vised"
        REVISIONS_REQUESTED = "REVISIONS_REQUESTED", "Revisions requested"

    teacher = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="cahier_entries",
    )
    subject_assignment = models.ForeignKey(
        "academics.SubjectAssignment",
        on_delete=models.CASCADE,
        related_name="cahier_entries",
        null=True,
        blank=True,
        help_text="Class and subject (from schedule).",
    )
    entry_date = models.DateField(help_text="Date of the lesson")
    lesson_topic_code = models.CharField(max_length=80, blank=True, help_text="Topic code from syllabus or national progression")
    title = models.CharField(max_length=300)
    objectives = models.TextField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    content_summary = models.TextField(blank=True)
    practical_application = models.BooleanField(default=False)
    integration_activity = models.BooleanField(default=False)
    attendance_snapshot = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vised_cahier_entries",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "Cahier de Texte entry"
        verbose_name_plural = "Cahier de Texte entries"
        indexes = [
            models.Index(fields=["teacher", "-entry_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.title} – {self.entry_date} ({self.get_status_display()})"


class Event(models.Model):
    """School event calendar (configurable)."""
    title = models.CharField(max_length=200)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=120, blank=True)
    is_public = models.BooleanField(default=True, help_text="Visible to portal users.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at"]
        verbose_name = "Event"
        verbose_name_plural = "Events"

    def __str__(self):
        return f"{self.title} ({self.start_at.date()})"


class TeacherTrainingEntry(models.Model):
    """In-service training / professional development log. RBAC: teacher sees only their own."""
    teacher = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="training_entries",
    )
    title = models.CharField(max_length=255)
    date = models.DateField()
    description = models.TextField(blank=True)
    document = models.FileField(
        upload_to=_training_entry_upload_to,
        blank=True,
        null=True,
        validators=[validate_document_file, validate_file_size_10mb],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Training log entry"
        verbose_name_plural = "Training log entries"
        indexes = [models.Index(fields=["teacher", "-date"])]

    def __str__(self):
        return f"{self.title} – {self.date}"


class AttendanceJustification(models.Model):
    """Parent-submitted justification for a student absence (excuse/medical)."""
    guardian = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_justifications",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="attendance_justifications",
    )
    attendance_date = models.DateField()
    reason = models.TextField(help_text="Reason for absence/lateness")
    document = models.FileField(
        upload_to=_justification_upload_to,
        blank=True,
        null=True,
        validators=[validate_document_file, validate_file_size_10mb],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attendance_date", "-created_at"]
        verbose_name = "Attendance justification"
        verbose_name_plural = "Attendance justifications"
        indexes = [
            models.Index(fields=["guardian", "student"]),
            models.Index(fields=["student", "attendance_date"]),
        ]

    def __str__(self):
        return f"{self.student} – {self.attendance_date}"


class PhotoUploadToken(models.Model):
    """Temporary token for uploading a profile photo from another device (e.g. phone)."""
    class Purpose(models.TextChoices):
        REGISTRATION = "registration", "Registration (new student/teacher)"
        PROFILE_UPDATE = "profile_update", "Profile update (existing)"

    token = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    photo = models.ImageField(upload_to=_photo_upload_token_upload_to, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.REGISTRATION)
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    teacher = models.ForeignKey(
        "people.TeacherProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Photo upload token"
        verbose_name_plural = "Photo upload tokens"

    def __str__(self):
        return str(self.token)


# Register portal enhancement models so migrations/admin discover them.
# These live in a separate module to keep this file focused.
try:
    from .portal_models import (  # noqa: E402,F401
        GuardianLinkInvitation,
        ParentStudentLink,
        PortalNotification,
        PortalPreferences,
        ParentMessage,
        PortalFeatureAccess,
        PortalSession,
        PortalAuditLog,
    )
except ImportError:
    pass

