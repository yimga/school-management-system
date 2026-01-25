from django.conf import settings
from django.utils import timezone
from django.db.models import Max
from apps.academics.models import Classroom, Department
from django.db import models
from django.utils import timezone
from datetime import timedelta
from apps.academics.models import Classroom, Department


def get_default_expiry():
    """Default expiry date: 30 days from now"""
    return timezone.now() + timedelta(days=30)


class Message(models.Model):
    """
    Internal messaging between users
    Support for threads, archiving, and priority
    """
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_messages'
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    
    is_read = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    
    parent_message = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['is_read']),
        ]
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
    
    def __str__(self):
        return f"{self.subject} - {self.sender.get_full_name()} to {self.recipient.get_full_name()}"
    
    @property
    def summary(self):
        """Short preview of message body"""
        return self.body[:100] + '...' if len(self.body) > 100 else self.body


class Announcement(models.Model):
    """
    School announcements for different audiences
    """
    class AnnouncementType(models.TextChoices):
        GENERAL = 'general', 'General'
        ACADEMIC = 'academic', 'Academic'
        EVENT = 'event', 'Event'
        ALERT = 'alert', 'Alert'
        HOLIDAY = 'holiday', 'Holiday'
        MAINTENANCE = 'maintenance', 'Maintenance'
    
    class Audience(models.TextChoices):
        ALL = 'all', 'All Users'
        STUDENTS = 'students', 'Students Only'
        TEACHERS = 'teachers', 'Teachers Only'
        PARENTS = 'all_parents', 'All Parents'
        STAFF = 'staff', 'Staff Only'
        SPECIFIC = 'specific', 'Specific Group'
    
    title = models.CharField(max_length=255)
    content = models.TextField()
    announcement_type = models.CharField(
        max_length=20,
        choices=AnnouncementType.choices,
        default=AnnouncementType.GENERAL
    )
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.ALL
    )
    
    is_active = models.BooleanField(default=True)
    is_urgent = models.BooleanField(default=False)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='announcements'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expiry_date = models.DateTimeField(default=get_default_expiry)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['is_active', 'expiry_date']),
        ]
        verbose_name = 'Announcement'
        verbose_name_plural = 'Announcements'
    
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
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, null=True, blank=True, related_name="announcements")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True, related_name="announcements")
    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.ALL)
    is_active = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
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
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.CLASSROOM)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, null=True, blank=True, related_name="message_threads")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True, related_name="message_threads")
    audience_role = models.CharField(max_length=30, blank=True, help_text="Optional: limit by role (e.g., PARENT, TEACHER)")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_threads'
    )
    
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='message_threads'
    )
    
    is_archived = models.BooleanField(default=False)
    last_message_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Message Thread'
        verbose_name_plural = 'Message Threads'
    
    def __str__(self):
        return self.title

    def touch_last_message(self):
        latest = self.messages.aggregate(latest=Max("created_at")).get("latest")
        self.last_message_at = latest or timezone.now()
        self.save(update_fields=["last_message_at", "updated_at"])


class ThreadMessage(models.Model):
    """
    Messages within a thread with audit-friendly soft delete/edit.
    """
    thread = models.ForeignKey(
        MessageThread,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='thread_messages'
    )
    
    content = models.TextField()
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
        ordering = ['-created_at']
        verbose_name = 'Thread Message'
        verbose_name_plural = 'Thread Messages'
    
    def __str__(self):
        return f"Message in {self.thread.title} by {self.author.get_full_name()}"

    def save(self, *args, **kwargs):
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


class AlertRule(models.Model):
    """
    User-defined alert rules for notifications
    """
    class Frequency(models.TextChoices):
        IMMEDIATE = 'immediate', 'Immediate'
        DAILY = 'daily', 'Daily'
        WEEKLY = 'weekly', 'Weekly'
        NEVER = 'never', 'Never'
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='alert_rules'
    )
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    condition = models.CharField(max_length=255)
    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.DAILY
    )
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Alert Rule'
        verbose_name_plural = 'Alert Rules'
        unique_together = ('user', 'name')
    
    def __str__(self):
        return f"{self.name} ({self.user.get_full_name()})"
