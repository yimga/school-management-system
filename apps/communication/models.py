"""
Communication app models. §2.4: broad except in _primary_school_id_for_user replaced with typed tuple.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Max, Q
from django.utils import timezone

from apps.academics.models import Classroom, Department
from apps.accounts.validators import (
    validate_kb_attachment_file,
    validate_file_size_10mb,
)

logger = logging.getLogger(__name__)

# Typed exceptions for user/school resolution (getattr, related access, query); §2.4
_COMMUNICATION_USER_SCHOOL_RESOLVE_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)
try:
    from django.db.utils import DatabaseError, OperationalError

    _COMMUNICATION_USER_SCHOOL_RESOLVE_ERRORS = (
        *_COMMUNICATION_USER_SCHOOL_RESOLVE_ERRORS,
        DatabaseError,
        OperationalError,
    )
except ImportError:
    pass


def contact_request_attachment_upload_to(instance, filename):
    """Tenant-scoped path for ContactRequestAttachment (Section 25.3)."""
    school_id = getattr(instance, "school_id", None) or (
        getattr(getattr(instance, "request", None), "school_id", None)
        if getattr(instance, "request", None)
        else None
    )
    if school_id is None:
        return f"tenant_uploads/communication/contact-requests/{filename}"
    return f"tenants/{school_id}/communication/contact-requests/{filename}"


def get_default_expiry():
    """Default expiry date: 30 days from now"""
    return timezone.now() + timedelta(days=30)


def _primary_school_id_for_user(user):
    if not user:
        return None
    try:
        student_profile = getattr(user, "student_profile", None)
        if student_profile and getattr(student_profile, "school_id", None):
            return student_profile.school_id
    except _COMMUNICATION_USER_SCHOOL_RESOLVE_ERRORS:
        pass
    try:
        teacher_profile = getattr(user, "teacher_profile", None)
        if teacher_profile and getattr(teacher_profile, "school_id", None):
            return teacher_profile.school_id
    except _COMMUNICATION_USER_SCHOOL_RESOLVE_ERRORS:
        pass
    try:
        return (
            user.school_memberships.order_by("-is_primary", "id")
            .values_list("school_id", flat=True)
            .first()
        )
    except _COMMUNICATION_USER_SCHOOL_RESOLVE_ERRORS:
        return None


def _pick_school_id(*candidates):
    for candidate in candidates:
        if candidate:
            return candidate
    return None


class Message(models.Model):
    """
    Internal messaging between users
    Support for threads, archiving, and priority
    """

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_messages",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="messages",
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    locale_target = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="BR-08: intended reader locale (recipient context) for i18n/audit.",
    )

    is_read = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)

    parent_message = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["sender", "-created_at"]),
            models.Index(fields=["is_read"]),
        ]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"{self.subject} - {self.sender.get_full_name()} to {self.recipient.get_full_name()}"

    @property
    def summary(self):
        """Short preview of message body"""
        return self.body[:100] + "..." if len(self.body) > 100 else self.body

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _pick_school_id(
                _primary_school_id_for_user(getattr(self, "sender", None)),
                _primary_school_id_for_user(getattr(self, "recipient", None)),
            )
        super().save(*args, **kwargs)


class MessageAttachment(models.Model):
    """File attachment on an internal :class:`Message`."""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="message_attachments/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.original_name


class DirectConversation(models.Model):
    """
    Staff–parent conversation; only staff can open. When staff close it, the loop closes
    and the parent can no longer reply. Parents contact school via Contact School form only.
    """

    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_conversations_as_user1",
    )
    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_conversations_as_user2",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="direct_conversations",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [
            ["user1", "user2"],
        ]
        indexes = [
            models.Index(fields=["user1", "user2"]),
            models.Index(fields=["closed_at"]),
        ]
        verbose_name = "Direct conversation (staff–parent)"
        verbose_name_plural = "Direct conversations (staff–parent)"

    def __str__(self):
        return f"{self.user1} ↔ {self.user2}" + (" (closed)" if self.closed_at else "")

    @classmethod
    def get_or_create_for(cls, user_a, user_b):
        """Get or create the conversation between two users (order-normalized)."""
        u1, u2 = (user_a, user_b) if user_a.pk < user_b.pk else (user_b, user_a)
        obj, _ = cls.objects.get_or_create(user1=u1, user2=u2)
        return obj

    @classmethod
    def is_closed(cls, user_a, user_b):
        """Return True if a conversation exists and is closed (does not create)."""
        u1, u2 = (user_a, user_b) if user_a.pk < user_b.pk else (user_b, user_a)
        conv = cls.objects.filter(user1=u1, user2=u2).first()
        return conv.closed_at is not None if conv else False

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _pick_school_id(
                _primary_school_id_for_user(getattr(self, "user1", None)),
                _primary_school_id_for_user(getattr(self, "user2", None)),
            )
        super().save(*args, **kwargs)


class Announcement(models.Model):
    """
    School-wide announcements. Creation is restricted to admins/leadership.
    Optional approval workflow: submissions can be PENDING_APPROVAL until approved.

    NOTE — distinct from ``portal.Announcement`` (a different concept, not a
    duplicate): that one is a simple date-windowed *banner* (BannerType colour,
    start/end_date, no school FK) rendered platform-wide by the portal context
    processor. This one is the rich, school-scoped, audience-targeted announcement
    with approval/status/is_urgent. Do not merge the two without a deliberate
    product decision + data migration.
    """

    class AnnouncementType(models.TextChoices):
        GENERAL = "general", "General"
        ACADEMIC = "academic", "Academic"
        EVENT = "event", "Event"
        ALERT = "alert", "Alert"
        HOLIDAY = "holiday", "Holiday"
        MAINTENANCE = "maintenance", "Maintenance"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        PUBLISHED = "published", "Published"

    class Audience(models.TextChoices):
        ALL = "all", "All Users"
        STUDENTS = "students", "Students Only"
        TEACHERS = "teachers", "Teachers Only"
        PARENTS = "all_parents", "All Parents"
        STAFF = "staff", "Staff Only"
        SPECIFIC = "specific", "Specific Group"

    title = models.CharField(max_length=255)
    content = models.TextField()
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    announcement_type = models.CharField(
        max_length=20,
        choices=AnnouncementType.choices,
        default=AnnouncementType.GENERAL,
    )
    audience = models.CharField(
        max_length=20, choices=Audience.choices, default=Audience.ALL
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PUBLISHED,
        help_text="Only published announcements are visible to the audience.",
    )

    is_active = models.BooleanField(default=True)
    is_urgent = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_announcements",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expiry_date = models.DateTimeField(default=get_default_expiry)

    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Future publish time; null = immediate. A periodic sender fans it out when due (Phase 4).",
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set once the fan-out sender has dispatched it (idempotency guard so it sends once).",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["is_active", "expiry_date"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"

    def __str__(self):
        return f"{self.title} ({self.get_announcement_type_display()})"

    @property
    def is_expired(self):
        """Check if announcement has expired"""
        return timezone.now() > self.expiry_date

    @property
    def time_to_expiry(self):
        """Days until announcement expires"""
        if self.is_expired:
            return 0
        delta = self.expiry_date - timezone.now()
        return delta.days

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _primary_school_id_for_user(
                getattr(self, "created_by", None)
            )
        super().save(*args, **kwargs)


class AnnouncementAuditLog(models.Model):
    """
    Audit log for school-wide announcements: who created, updated, approved,
    or deactivated. Supports accountability and compliance.
    """

    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        SUBMITTED_FOR_APPROVAL = "submitted_for_approval", "Submitted for approval"
        APPROVED = "approved", "Approved"
        PUBLISHED = "published", "Published"
        DEACTIVATED = "deactivated", "Deactivated"

    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcement_audit_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcement_audit_entries",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["announcement", "-created_at"]),
            models.Index(fields=["action"]),
        ]
        verbose_name = "Announcement audit log"
        verbose_name_plural = "Announcement audit logs"

    def __str__(self):
        return f"{self.get_action_display()} by {self.user} on {self.announcement_id}"

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _pick_school_id(
                getattr(self.announcement, "school_id", None)
                if getattr(self, "announcement", None)
                else None,
                _primary_school_id_for_user(getattr(self, "user", None)),
            )
        super().save(*args, **kwargs)


def log_announcement_audit(announcement, user, action: str, notes: str = ""):
    """Record an audit entry for an announcement (create, update, approve, deactivate)."""
    if not announcement or not action:
        return
    action_val = (action or "").strip().lower().replace(" ", "_")
    valid = [a[0] for a in AnnouncementAuditLog.Action.choices]
    if action_val not in valid:
        action_val = AnnouncementAuditLog.Action.UPDATED
    AnnouncementAuditLog.objects.create(
        announcement=announcement,
        school=getattr(announcement, "school", None),
        user=user,
        action=action_val,
        notes=(notes or "")[:500],
    )


class ClassAnnouncement(models.Model):
    """
    Scoped announcements/comments for a class or department with RBAC-aware visibility.
    """

    class Audience(models.TextChoices):
        PARENTS = "parents", "Parents"
        TEACHERS = "teachers", "Teachers"
        STAFF = "staff", "Staff"
        ALL = "all", "All"

    title = models.CharField(max_length=200)
    body = models.TextField()
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="class_announcements",
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )
    audience = models.CharField(
        max_length=20, choices=Audience.choices, default=Audience.ALL
    )
    is_active = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["audience", "is_active"]),
        ]

    def __str__(self):
        scope = self.classroom or self.department or "General"
        return f"{self.title} ({scope})"

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _pick_school_id(
                getattr(self.classroom, "school_id", None)
                if getattr(self, "classroom", None)
                else None,
                getattr(self.department, "school_id", None)
                if getattr(self, "department", None)
                else None,
                _primary_school_id_for_user(getattr(self, "created_by", None)),
            )
        super().save(*args, **kwargs)


class MessageThread(models.Model):
    """
    Group message threads for class / department / role communication.
    """

    class Scope(models.TextChoices):
        CLASSROOM = "CLASSROOM", "Classroom"
        DEPARTMENT = "DEPARTMENT", "Department"
        ROLE = "ROLE", "Role-based"
        GLOBAL = "GLOBAL", "Global"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="message_threads",
    )
    scope = models.CharField(
        max_length=20, choices=Scope.choices, default=Scope.CLASSROOM
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="message_threads",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="message_threads",
    )
    audience_role = models.CharField(
        max_length=30,
        blank=True,
        help_text="Optional: limit by role (e.g., PARENT, TEACHER)",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_threads",
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="message_threads"
    )

    is_archived = models.BooleanField(default=False)
    last_message_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Message Thread"
        verbose_name_plural = "Message Threads"

    def __str__(self):
        return self.title

    def touch_last_message(self):
        latest = self.messages.aggregate(latest=Max("created_at")).get("latest")
        self.last_message_at = latest or timezone.now()
        self.save(update_fields=["last_message_at", "updated_at"])

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _pick_school_id(
                getattr(self.classroom, "school_id", None)
                if getattr(self, "classroom", None)
                else None,
                getattr(self.department, "school_id", None)
                if getattr(self, "department", None)
                else None,
                _primary_school_id_for_user(getattr(self, "created_by", None)),
            )
        super().save(*args, **kwargs)


class ThreadMessage(models.Model):
    """
    Messages within a thread with audit-friendly soft delete/edit.
    """

    thread = models.ForeignKey(
        MessageThread, on_delete=models.CASCADE, related_name="messages"
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="thread_messages",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="thread_messages",
    )

    content = models.TextField()
    locale_target = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="BR-08: intended reader locale (e.g. parent UI language) for translation/audit.",
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_thread_messages",
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_thread_messages",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Thread Message"
        verbose_name_plural = "Thread Messages"

    def __str__(self):
        return f"Message in {self.thread.title} by {self.author.get_full_name()}"

    def save(self, *args, **kwargs):
        self.school_id = _pick_school_id(
            getattr(self.thread, "school_id", None)
            if getattr(self, "thread", None)
            else None,
            self.school_id,
            _primary_school_id_for_user(getattr(self, "author", None)),
        )
        new = self.pk is None
        if new:
            self.thread.last_message_at = timezone.now()
            self.thread.save(update_fields=["last_message_at", "updated_at"])
        else:
            self.edited_at = timezone.now()
        super().save(*args, **kwargs)


class ThreadReadState(models.Model):
    """
    Tracks last read per user/thread for unread counts.
    """

    thread = models.ForeignKey(
        MessageThread,
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="thread_read_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="thread_read_states",
    )
    last_read_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("thread", "user")
        ordering = ["-updated_at"]

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _pick_school_id(
                getattr(self.thread, "school_id", None)
                if getattr(self, "thread", None)
                else None,
                _primary_school_id_for_user(getattr(self, "user", None)),
            )
        super().save(*args, **kwargs)


class AlertRule(models.Model):
    """
    User-defined alert rules for notifications
    """

    class Frequency(models.TextChoices):
        IMMEDIATE = "immediate", "Immediate"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        NEVER = "never", "Never"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_rules"
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_rules",
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    condition = models.CharField(max_length=255)
    frequency = models.CharField(
        max_length=20, choices=Frequency.choices, default=Frequency.DAILY
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Alert Rule"
        verbose_name_plural = "Alert Rules"
        unique_together = ("user", "name")

    def __str__(self):
        return f"{self.name} ({self.user.get_full_name()})"

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _primary_school_id_for_user(getattr(self, "user", None))
        super().save(*args, **kwargs)


class ContactRequest(models.Model):
    """
    Parent/guardian request to speak with staff.
    Routed to secretary/executive assistant/virtual assistant for triage, then assigned to the right person.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        TRIAGED = "TRIAGED", "Triaged"
        ASSIGNED = "ASSIGNED", "Assigned"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    class Channel(models.TextChoices):
        PHONE = "PHONE", "Phone call"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        EMAIL = "EMAIL", "Email"
        IN_PERSON = "IN_PERSON", "In-person"

    class Audience(models.TextChoices):
        TEACHER = "TEACHER", "Teacher"
        LEADERSHIP = "LEADERSHIP", "Leadership"
        FINANCE = "FINANCE", "Finance/Bursar"
        REGISTRAR = "REGISTRAR", "Registrar/Admissions"
        IT = "IT", "IT Support"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="contact_requests",
    )

    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contact_requests_created",
        help_text="Parent/guardian who submitted the request.",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_requests",
        help_text="Optional: the student this request is about.",
    )

    # Confirmation details (parents can correct these even if account profile is incomplete)
    contact_name = models.CharField(max_length=160)
    contact_phone = models.CharField(max_length=60, blank=True)
    contact_whatsapp = models.CharField(max_length=60, blank=True)
    contact_email = models.EmailField(blank=True)

    audience = models.CharField(
        max_length=30, choices=Audience.choices, default=Audience.TEACHER
    )
    preferred_channel = models.CharField(
        max_length=20, choices=Channel.choices, default=Channel.WHATSAPP
    )
    subject = models.CharField(max_length=200)
    message = models.TextField()

    desired_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_requests_desired",
        help_text="Optional: specific user the parent wants to speak to.",
    )

    triage_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_requests_triaged",
        help_text="Secretary/executive assistant/virtual assistant handling triage.",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_requests_assigned",
        help_text="Staff member responsible for contacting the parent.",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )

    triage_notes = models.TextField(blank=True)
    resolution_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["parent", "-created_at"]),
            models.Index(fields=["assigned_to", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.subject} · {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _pick_school_id(
                getattr(self.student, "school_id", None)
                if getattr(self, "student", None)
                else None,
                _primary_school_id_for_user(getattr(self, "parent", None)),
                _primary_school_id_for_user(getattr(self, "assigned_to", None)),
                _primary_school_id_for_user(getattr(self, "triage_owner", None)),
            )
        super().save(*args, **kwargs)


class ContactRequestAttachment(models.Model):
    request = models.ForeignKey(
        ContactRequest, on_delete=models.CASCADE, related_name="attachments"
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="contact_request_attachments",
    )
    file = models.FileField(
        upload_to=contact_request_attachment_upload_to,
        validators=[validate_kb_attachment_file, validate_file_size_10mb],
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_request_attachments_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def save(self, *args, **kwargs):
        if not self.school_id:
            self.school_id = _pick_school_id(
                getattr(self.request, "school_id", None)
                if getattr(self, "request", None)
                else None,
                _primary_school_id_for_user(getattr(self, "uploaded_by", None)),
            )
        super().save(*args, **kwargs)


# -----------------------------------------------------------------------------
# AI narrative feedback: achievement events → LLM-generated parent message (teacher-approved)
# -----------------------------------------------------------------------------


class AchievementEvent(models.Model):
    """Trigger for AI narrative: e.g. 3 days perfect attendance, grade improved in Math."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="achievement_events",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="achievement_events",
    )
    event_type = models.CharField(
        max_length=80, help_text="e.g. perfect_attendance_3d, grade_improved_math"
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "student", "-created_at"])]

    def __str__(self):
        return f"{self.student_id} — {self.event_type}"


class NarrativeFeedback(models.Model):
    """AI-generated narrative for parents; teacher approves before sending."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        SENT = "SENT", "Sent"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="narrative_feedbacks",
    )
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        related_name="narrative_feedbacks",
    )
    achievement_event = models.ForeignKey(
        AchievementEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="narrative_feedbacks",
    )
    message_text = models.TextField(
        help_text="AI-generated or edited message for parent"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_narrative_feedbacks",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self):
        return f"{self.student_id} — {self.status}"


# Plan VI: Social feed (parent/teacher loop) — announcements, achievements, interventions
class FeedItem(models.Model):
    """Single item in the parent/teacher feed (announcements, achievements, risk/interventions)."""

    class ItemType(models.TextChoices):
        ANNOUNCEMENT = "announcement", "Announcement"
        ACHIEVEMENT = "achievement", "Achievement"
        RISK = "risk", "Risk / intervention"
        EVENT = "event", "Event"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="feed_items",
    )
    item_type = models.CharField(max_length=20, choices=ItemType.choices, db_index=True)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    link_url = models.CharField(max_length=500, blank=True)
    link_label = models.CharField(max_length=120, blank=True)
    student = models.ForeignKey(
        "people.StudentProfile",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="feed_items",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_feed_items",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["student", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_item_type_display()}: {self.title}"


# Plan VI: WhatsApp / outbound message queue (scaffold; needs Meta credentials in prod)
class OutboundMessageQueue(models.Model):
    """Queue for outbound WhatsApp/SMS messages; provider sends when configured."""

    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS = "sms", "SMS"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="outbound_message_queue",
        null=True,
        blank=True,
    )
    channel = models.CharField(
        max_length=20, choices=Channel.choices, default=Channel.WHATSAPP
    )
    recipient_identifier = models.CharField(
        max_length=255, help_text="Phone or WhatsApp ID"
    )
    body = models.TextField()
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("sent", "Sent"),
            ("failed", "Failed"),
            ("retrying", "Retrying"),
        ],
        db_index=True,
    )
    retry_count = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(max_length=255, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} to {self.recipient_identifier}: {self.status}"


class CommunicationTemplate(models.Model):
    """Per-tenant notification template override.

    Pairs with the platform-wide code-level catalog at
    ``apps.communication.template_catalog``. Resolution order in
    ``notification_service``:

      1. CommunicationTemplate for ``(school, key, locale)`` if ``is_active``
      2. CommunicationTemplate for ``(school=None, key, locale)`` (platform fallback)
      3. ``COMMUNICATION_TEMPLATES[key]`` from the code catalog
      4. Hard fallback (subject = key, body = "(template missing)")

    Tenant admins edit overrides via the manager-portal Comms settings;
    the platform-wide null-school row is a control-plane override used
    to test new templates before promoting them into the code catalog.
    """

    class Sensitivity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="communication_templates",
        null=True,
        blank=True,
        help_text="Null = platform-wide override; otherwise scoped to the tenant.",
    )
    key = models.CharField(
        max_length=120,
        db_index=True,
        help_text="Catalog key (e.g. 'attendance.absent_today'). Must match COMMUNICATION_TEMPLATES.",
    )
    subject_template = models.CharField(max_length=200, blank=True)
    body_template = models.TextField()
    channels = models.JSONField(
        default=list,
        blank=True,
        help_text="List of channel codes this override applies to. Empty = all channels declared by the catalog entry.",
    )
    audience = models.CharField(max_length=40, blank=True)
    sensitivity = models.CharField(
        max_length=10,
        choices=Sensitivity.choices,
        default=Sensitivity.MEDIUM,
    )
    is_active = models.BooleanField(default=True)
    locale = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional BCP-47 locale (e.g. 'fr-CM'). Empty = applies to all locales.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Communication template override"
        verbose_name_plural = "Communication template overrides"
        indexes = [
            models.Index(fields=["school", "key", "is_active"]),
            models.Index(fields=["key", "locale", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "key", "locale"],
                name="comm_tmpl_school_key_locale_uniq",
            ),
        ]

    def __str__(self):
        scope = self.school_id or "platform"
        return f"{self.key} @ {scope} ({self.locale or 'any'})"


class SmsSendLog(models.Model):
    """Provider-level SMS idempotency send-log (audit GAP-7).

    A retry that reaches the provider twice can double-send a real SMS. This is
    the persisted send-log the SMS path gates on (via the partial-unique
    ``idempotency_key``) BEFORE the provider call, so the same logical send is
    never dispatched twice.

    PII contract: we store ``recipient_hash`` only — an sha256 hex prefix of the
    E.164 number, never the raw phone (mirrors ``models_consent`` /
    ``models_delivery_receipt``).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    idempotency_key = models.CharField(max_length=128, blank=True)
    recipient_hash = models.CharField(
        max_length=64,
        help_text="sha256 hex prefix of the E.164 number — never the raw phone.",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    provider = models.CharField(max_length=32, blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_sms_send_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["recipient_hash", "created_at"]),
        ]

    def __str__(self):
        return f"SmsSendLog[{self.get_status_display()}] {self.recipient_hash}"


class NotificationPreference(models.Model):
    """Granular per-user notification preferences (audit MED-4).

    Reinstates the deleted ``people.NotificationPreference`` so Phase 3 can
    ENFORCE per-category mute, per-category channel overrides, quiet hours, and
    digest cadence at send time.
    """

    class Category(models.TextChoices):
        GRADES = "grades", "Grades"
        FEES = "fees", "Fees"
        ATTENDANCE = "attendance", "Attendance"
        ANNOUNCEMENTS = "announcements", "Announcements"
        MESSAGES = "messages", "Messages"
        DISCIPLINE = "discipline", "Discipline"
        ADMISSIONS = "admissions", "Admissions"
        SYSTEM = "system", "System"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        IN_APP = "in_app", "In-app"
        PUSH = "push", "Push"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Cadence(models.TextChoices):
        IMMEDIATE = "immediate", "Immediate"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    muted_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Category values the user muted.",
    )
    channel_overrides = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional {category: [channel, ...]}; empty = channel defaults.",
    )
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    digest_cadence = models.CharField(
        max_length=16,
        choices=Cadence.choices,
        default=Cadence.IMMEDIATE,
    )
    timezone = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"NotificationPreference[{self.user_id}]"

    def is_muted(self, category) -> bool:
        """True if the given category is in the user's muted list."""
        return category in (self.muted_categories or [])

    def allows(self, category, channel) -> bool:
        """Whether a notification in ``category`` may go out on ``channel``.

        False if the category is muted; otherwise, if a channel override exists
        for the category, the channel must be in that override list; otherwise
        the channel defaults apply (allowed).
        """
        if self.is_muted(category):
            return False
        overrides = self.channel_overrides or {}
        if category in overrides:
            return channel in (overrides.get(category) or [])
        return True

    def in_quiet_hours(self, when_local_time) -> bool:
        """True if ``when_local_time`` falls within the configured quiet window.

        Both ends must be set. Handles a window that wraps past midnight (e.g.
        22:00 → 07:00).
        """
        start = self.quiet_hours_start
        end = self.quiet_hours_end
        if start is None or end is None:
            return False
        if start <= end:
            return start <= when_local_time <= end
        # Wraps past midnight: inside if before end OR after start.
        return when_local_time >= start or when_local_time <= end


# Register video conferencing models under the communication app so migrations
# and app model loading include them consistently.
from .video_conferencing import (  # noqa: E402,F401
    BreakoutRoom,
    SessionParticipant,
    SessionRecording,
    VirtualClassroom,
)

# Cross-channel consent log + SMS/WhatsApp delivery receipts (audit residual
# closeout). Re-exported here so model loading + migrations include them.
from .models_consent import (  # noqa: E402,F401
    ConsentAction,
    ConsentChannel,
    ConsentEvent,
    ConsentEventReadOnlyError,
)
from .models_delivery_receipt import (  # noqa: E402,F401
    DeliveryChannel,
    MessageDeliveryReceipt,
)
from .models_web_push import WebPushSubscription  # noqa: E402,F401
