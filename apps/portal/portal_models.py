"""
Phase 8 Task 7: Portal Enhancements
Parent portal linking, guardian management, child-parent relationships
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class GuardianLinkInvitation(models.Model):
    """Invitation for parents/guardians to link to students"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]
    
    student_id = models.IntegerField()
    parent_email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    token = models.CharField(max_length=100, unique=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.IntegerField()  # Teacher or admin who created
    
    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['parent_email']),
            models.Index(fields=['student_id']),
        ]
    
    def is_expired(self):
        """Check if invitation has expired"""
        return timezone.now() > self.expires_at and self.status == 'pending'
    
    def __str__(self):
        return f"Invitation for {self.parent_email} - {self.student_id}"


class ParentStudentLink(models.Model):
    """Link between parent/guardian and student"""
    
    RELATIONSHIP_CHOICES = [
        ('parent', 'Parent'),
        ('guardian', 'Guardian'),
        ('foster_parent', 'Foster Parent'),
        ('relative', 'Relative'),
    ]
    
    parent_id = models.IntegerField()
    student_id = models.IntegerField()
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, default='parent')
    is_primary = models.BooleanField(default=False)
    access_level = models.CharField(
        max_length=20,
        choices=[
            ('full', 'Full Access'),
            ('limited', 'Limited Access'),
            ('read_only', 'Read Only'),
        ],
        default='limited'
    )
    linked_at = models.DateTimeField(auto_now_add=True)
    linked_by = models.IntegerField()  # User who created link
    
    class Meta:
        unique_together = ('parent_id', 'student_id')
        ordering = ['-linked_at']
        indexes = [
            models.Index(fields=['parent_id', 'student_id']),
            models.Index(fields=['parent_id']),
        ]
    
    def __str__(self):
        return f"{self.parent_id} - {self.student_id} ({self.relationship})"


class PortalNotification(models.Model):
    """Notifications for parents on portal"""
    
    NOTIFICATION_TYPES = [
        ('grade', 'Grade Update'),
        ('attendance', 'Attendance Alert'),
        ('fee', 'Fee Due'),
        ('behavior', 'Behavior Report'),
        ('announcement', 'Announcement'),
        ('event', 'Event Notice'),
    ]
    
    parent_id = models.IntegerField()
    student_id = models.IntegerField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    related_id = models.IntegerField(null=True, blank=True)  # Foreign key to source
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['parent_id', 'is_read']),
            models.Index(fields=['student_id']),
        ]
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.read_at = timezone.now()
        self.save()
    
    def __str__(self):
        return f"{self.title} - {self.parent_id}"


class PortalPreferences(models.Model):
    """Parent preferences for portal experience"""
    
    parent_id = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='portal_prefs',
    )
    notification_email = models.BooleanField(default=True)
    notification_sms = models.BooleanField(default=False)
    language = models.CharField(max_length=10, default='en')
    theme = models.CharField(
        max_length=20,
        choices=[
            ('light', 'Light'),
            ('dark', 'Dark'),
            ('auto', 'Auto'),
        ],
        default='light'
    )
    show_grades = models.BooleanField(default=True)
    show_attendance = models.BooleanField(default=True)
    show_fees = models.BooleanField(default=True)
    show_announcements = models.BooleanField(default=True)
    dashboard_widgets = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Preferences for {self.parent_id}"


class ParentMessage(models.Model):
    """Messages between parent and school"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('read', 'Read'),
        ('archived', 'Archived'),
    ]
    
    sender_id = models.IntegerField()
    recipient_id = models.IntegerField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient_id', 'status']),
        ]
    
    def __str__(self):
        return f"{self.subject} - {self.sender_id} to {self.recipient_id}"


class PortalFeatureAccess(models.Model):
    """Control which features parents can access"""
    
    FEATURES = [
        ('view_grades', 'View Grades'),
        ('view_attendance', 'View Attendance'),
        ('view_fees', 'View Fees'),
        ('download_reports', 'Download Reports'),
        ('message_teacher', 'Message Teachers'),
        ('register_events', 'Register for Events'),
        ('update_profile', 'Update Profile'),
    ]
    
    parent_id = models.IntegerField()
    feature = models.CharField(max_length=50, choices=FEATURES)
    is_enabled = models.BooleanField(default=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('parent_id', 'feature')
        ordering = ['feature']
    
    def __str__(self):
        return f"{self.parent_id} - {self.feature}: {self.is_enabled}"


class PortalSession(models.Model):
    """Track parent portal sessions for security"""
    
    parent_id = models.IntegerField()
    session_token = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    login_at = models.DateTimeField(auto_now_add=True)
    logout_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    device_type = models.CharField(max_length=50, default='unknown')
    
    class Meta:
        ordering = ['-login_at']
        indexes = [
            models.Index(fields=['parent_id', 'is_active']),
            models.Index(fields=['session_token']),
        ]
    
    def __str__(self):
        return f"Session {self.parent_id} - {self.login_at}"


class PortalAuditLog(models.Model):
    """Audit log for parent portal activities"""
    
    ACTION_TYPES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('view_grades', 'View Grades'),
        ('download_report', 'Download Report'),
        ('send_message', 'Send Message'),
        ('update_preferences', 'Update Preferences'),
    ]
    
    parent_id = models.IntegerField()
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    description = models.TextField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['parent_id', 'action']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.parent_id} - {self.action} - {self.timestamp}"
