"""
Phase 8 Task 2: Models for Advanced Analytics
Extended models for Grade Import and performance tracking
"""

from django.db import models
from django.conf import settings
from django.utils import timezone

from apps.accounts.validators import validate_grade_import_file, validate_file_size_5mb


class GradeImportRecord(models.Model):
    """Track grade import operations (simplified record to avoid model name conflicts)

    NOTE: Renamed from `GradeImportJob` to avoid conflicting with the primary
    `GradeImportJob` model in `apps.analytics.models`. Tests that expect the
    legacy/simplified model should import `GradeImportRecord` instead.
    """

    STATUSES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('PARTIAL', 'Partial'),
    ]

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    file_name = models.CharField(max_length=255)
    file_path = models.FileField(
        upload_to='grade_imports/',
        null=True,
        blank=True,
        validators=[validate_grade_import_file, validate_file_size_5mb],
    )
    status = models.CharField(max_length=15, choices=STATUSES, default='PENDING')
    total_records = models.IntegerField(default=0)
    imported_records = models.IntegerField(default=0)
    failed_records = models.IntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Grade Import Record'
        verbose_name_plural = 'Grade Import Records'
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.file_name} - {self.status}"


class PerformanceMetrics(models.Model):
    """Cache computed performance metrics"""
    
    from apps.people.models import StudentProfile
    
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='performance_metrics'
    )
    
    average_score = models.FloatField(default=0)
    total_evaluations = models.IntegerField(default=0)
    pass_rate = models.FloatField(default=0)
    trend = models.CharField(
        max_length=20,
        choices=[
            ('IMPROVING', 'Improving'),
            ('DECLINING', 'Declining'),
            ('STABLE', 'Stable'),
        ],
        default='STABLE'
    )
    risk_level = models.CharField(
        max_length=10,
        choices=[
            ('LOW', 'Low'),
            ('MEDIUM', 'Medium'),
            ('HIGH', 'High'),
            ('CRITICAL', 'Critical'),
        ],
        default='LOW'
    )
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Performance Metrics'
        verbose_name_plural = 'Performance Metrics'
    
    def __str__(self):
        return f"{self.student} - {self.average_score:.1f}%"
